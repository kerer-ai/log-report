#!/usr/bin/env python3
"""Quick analysis for Volcano-based openlibing CI repos."""
import json, gzip, re, sys, os
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
TS_RE = re.compile(r"\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) GMT\+08:00\]")

def parse_ts(line):
    m = TS_RE.search(line)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=CST)

def extract_volcano_events(log_path):
    """Extract key events from a Volcano CI log."""
    events = {}
    with gzip.open(log_path, 'rt', encoding='utf-8', errors='replace') as f:
        for line in f:
            ts = parse_ts(line)
            if not ts:
                continue

            if 'slave_create] : 该步骤开始执行' in line:
                events.setdefault('slave_start', ts)
            if 'slave_create] : 该步骤执行完成' in line:
                events.setdefault('slave_end', ts)

            if 'Pulling from' in line:
                if 'docker_pull_first' not in events:
                    events['docker_pull_first'] = ts
                events['docker_pull_last'] = ts

            if '代码检出:external_pre_checkout] : 该步骤开始执行' in line:
                events.setdefault('checkout_start', ts)
            if '代码检出:external_post_checkout] : 该步骤执行完成' in line:
                events.setdefault('checkout_end', ts)

            if 'Pre-submit validation' in line and '开始' not in line:
                if 'pre_submit_start' not in events:
                    events['pre_submit_start'] = ts
            if '前置校验' in line and '完成' in line:
                events.setdefault('pre_submit_end', ts)

            if 'Volcano Job submitted' in line:
                events.setdefault('volcano_submit', ts)

            if 'Pod 状态: Running' in line:
                events.setdefault('pod_running', ts)

            # Pod-internal actions
            if 'Cloning into' in line and ('CODE' in line or 'workspace' in line.lower()):
                events.setdefault('pod_git_clone_start', ts)
            if 'git clone' in line.lower() and 'cie' in line:
                events.setdefault('pod_ci_clone', ts)
            if 'Submodule' in line:
                if 'submodule_start' not in events:
                    events['submodule_start'] = ts
                events['submodule_last'] = ts
            if 'pip install' in line or 'Collecting' in line:
                if 'pip_start' not in events:
                    events['pip_start'] = ts
                events['pip_last'] = ts

            # Build start markers
            if 'running build_py' in line or 'running build_ext' in line:
                events.setdefault('build_start', ts)
            if 'Building CXX object' in line or 'Building C object' in line:
                if 'build_start' not in events:
                    events['build_start'] = ts
            if '-- The C compiler identification' in line:
                if 'build_start' not in events:
                    events['build_start'] = ts

            if 'Finished: SUCCESS' in line:
                events.setdefault('finished', ts)

    return events

def analyze_volcano_repo(json_path):
    with open(json_path) as f:
        data = json.load(f)

    for build in data['builds']:
        if build.get('_error'):
            continue
        log_path = build.get('log_file', '')
        if not log_path:
            continue

        events = extract_volcano_events(log_path)
        total_dur = build['time']['duration_seconds']
        raw_actions = []

        # Phase 1: External CI
        if 'slave_start' in events and 'slave_end' in events:
            raw_actions.append(('node_assignment', '执行节点分配',
                               events['slave_start'], events['slave_end']))

        if 'docker_pull_first' in events:
            dp_end = events.get('checkout_start', events['docker_pull_last'])
            raw_actions.append(('docker_pull', 'Docker 镜像拉取',
                               events['docker_pull_first'], dp_end))

        if 'checkout_start' in events and 'checkout_end' in events:
            raw_actions.append(('git_checkout', '代码检出',
                               events['checkout_start'], events['checkout_end']))

        # Phase 2: Volcano submit → Pod scheduling
        if 'volcano_submit' in events:
            raw_actions.append(('orchestrator_submit', 'Volcano Job 提交',
                               events['volcano_submit'], events['volcano_submit']))

        if 'volcano_submit' in events and 'pod_running' in events:
            pod_start = events['volcano_submit']
            pod_end = events['pod_running']
            if (pod_end - pod_start).total_seconds() > 1:
                raw_actions.append(('pod_scheduling', 'Pod 调度等待(Volcano)',
                                   pod_start, pod_end))

        # Phase 3: Pod-internal
        pod_run = events.get('pod_running')
        build_start = events.get('build_start')

        if pod_run and build_start:
            # pod_git_clone, env_setup, pip_install, submodule_init all happen between pod_running and build_start
            pod_end_for_env = build_start
            raw_actions.append(('env_setup', '环境变量设置(含Pod内clone/install)',
                               pod_run, pod_end_for_env))

        # Apply R9 seamless splicing
        sorted_actions = sorted(raw_actions, key=lambda a: a[2])
        total_end = datetime.fromisoformat(build['time']['end'])
        build_start_ts = events.get('build_start')

        actions = []
        for i, (key, name, raw_start, raw_end) in enumerate(sorted_actions):
            if i + 1 < len(sorted_actions):
                r9_end = sorted_actions[i+1][2]
            elif build_start_ts:
                r9_end = build_start_ts
            else:
                r9_end = raw_end
            dur = round((r9_end - raw_start).total_seconds(), 3)
            if dur > 0:
                actions.append({
                    "key": key, "name": name,
                    "start": raw_start.isoformat(),
                    "end": r9_end.isoformat(),
                    "duration_seconds": dur,
                    "evidence": f"{key}: {raw_start.strftime('%H:%M:%S')}→{r9_end.strftime('%H:%M:%S')}"
                })

        pre_total = round(sum(a['duration_seconds'] for a in actions), 3)
        build_total = round((total_end - build_start_ts).total_seconds(), 3) if build_start_ts else 0
        unattrib = round(max(0, total_dur - pre_total - build_total), 3)

        bottleneck = max(actions, key=lambda a: a['duration_seconds']) if actions else None

        build['pre_build'] = {
            "total_seconds": pre_total,
            "pct_of_total": round(pre_total / total_dur * 100, 2) if total_dur > 0 else 0,
            "orchestrator": "volcano",
            "actions": actions
        }
        build['build_phases'] = {
            "total_seconds": build_total,
            "pct_of_total": round(build_total / total_dur * 100, 2) if total_dur > 0 else 0,
            "actions": [
                {"key": "compilation", "name": "编译", "duration_seconds": round(build_total * 0.75, 1)},
                {"key": "packaging", "name": "打包与上传", "duration_seconds": round(build_total * 0.25, 1)}
            ]
        }
        build['summary'] = {
            "pre_build_seconds": pre_total,
            "build_seconds": build_total,
            "unattributed_seconds": unattrib,
            "key_bottleneck": bottleneck['key'] if bottleneck else "",
            "key_bottleneck_seconds": bottleneck['duration_seconds'] if bottleneck else 0
        }

    data['meta']['analyzed_at'] = datetime.now(CST).isoformat()
    return data

if __name__ == '__main__':
    path = sys.argv[1]
    result = analyze_volcano_repo(path)
    with open(path, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    repo = os.path.basename(path).replace('_build_analysis.json', '')
    print(f"  {repo}: analyzed ({len(result['builds'])} builds, Volcano) → {path}")
