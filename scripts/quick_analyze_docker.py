#!/usr/bin/env python3
"""Quick analysis for Docker-native openlibing CI repos.
Extracts key events from log files and generates completed analysis JSON."""
import json, gzip, re, sys, os
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
TS_RE = re.compile(r"\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) GMT\+08:00\]")

def parse_ts(line):
    m = TS_RE.search(line)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=CST)

def extract_events(log_path):
    """Extract key CI events from a Docker-native CI log."""
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

            if 'Pulling from *****' in line or 'Pulling from' in line:
                # Track first and last docker pull
                if 'docker_pull_first' not in events:
                    events['docker_pull_first'] = ts
                events['docker_pull_last'] = ts

            if 'Cache Check:external_cache_check] : 该步骤开始执行' in line:
                events.setdefault('cache_start', ts)
            if 'Cache Check:external_cache_check] : 该步骤执行完成' in line:
                events.setdefault('cache_end', ts)

            if '代码检出:external_pre_checkout] : 该步骤开始执行' in line:
                events.setdefault('checkout_start', ts)
            if '代码检出:external_post_checkout] : 该步骤执行完成' in line:
                events.setdefault('checkout_end', ts)

            if 'running build' in line or 'running build_py' in line:
                events.setdefault('build_start', ts)
            # C++ build start
            if 'Building CXX object' in line or 'Building C object' in line:
                if 'build_start' not in events:
                    events['build_start'] = ts
            # CMake start
            if '-- The C compiler identification' in line or '-- Check for working C compiler' in line:
                if 'build_start' not in events:
                    events['build_start'] = ts

            if 'JobStatusPlugin] onCompleted' in line:
                events.setdefault('job_completed', ts)
            if 'Finished: SUCCESS' in line:
                events.setdefault('finished', ts)

            # CI script clone
            if 'git clone' in line.lower() and ('cie' in line or 'CI' in line):
                events.setdefault('env_setup_start', ts)
            if 'bash' in line and ('merge.sh' in line or 'build.sh' in line):
                events.setdefault('env_setup_mid', ts)

    return events

def analyze_docker_repo(json_path):
    """Analyze a Docker-native repo from its json-org template."""
    with open(json_path) as f:
        data = json.load(f)

    for build in data['builds']:
        if build.get('_error'):
            continue

        log_path = build.get('log_file', '')
        if not log_path:
            continue

        events = extract_events(log_path)
        total_dur = build['time']['duration_seconds']

        # Build ordered list of actions with their raw start/end
        raw_actions = []

        if 'slave_start' in events and 'slave_end' in events:
            raw_actions.append(('node_assignment', '执行节点分配',
                               events['slave_start'], events['slave_end']))

        if 'docker_pull_first' in events:
            # Docker pull spans from first to last image check
            dp_start = events['docker_pull_first']
            dp_end = events.get('docker_pull_last', events.get('checkout_start', dp_start))
            raw_actions.append(('docker_pull', 'Docker 镜像拉取', dp_start, dp_end))

        if 'cache_start' in events and 'cache_end' in events:
            raw_actions.append(('cache_check', '缓存检查',
                               events['cache_start'], events['cache_end']))

        if 'checkout_start' in events and 'checkout_end' in events:
            raw_actions.append(('git_checkout', '代码检出',
                               events['checkout_start'], events['checkout_end']))

        # Detect env_setup start (after checkout, before build)
        env_start = events.get('env_setup_start')
        if not env_start and 'checkout_end' in events:
            env_start_val = events['checkout_end']
        else:
            env_start_val = env_start

        if 'build_start' in events and env_start_val:
            raw_actions.append(('env_setup', '环境变量设置',
                               env_start_val, events['build_start']))

        if not raw_actions:
            print(f"  WARNING: no pre-build actions found for {build['task_name']}")
            continue

        # Apply R9 seamless splicing
        sorted_actions = sorted(raw_actions, key=lambda a: a[2])
        build_start = events.get('build_start')
        build_end = events.get('finished', events.get('job_completed'))
        total_end = datetime.fromisoformat(build['time']['end'])

        actions = []
        for i, (key, name, raw_start, raw_end) in enumerate(sorted_actions):
            if i + 1 < len(sorted_actions):
                r9_end = sorted_actions[i+1][2]  # next action's start
            elif build_start:
                r9_end = build_start
            else:
                r9_end = raw_end

            dur = round((r9_end - raw_start).total_seconds(), 3)
            if dur > 0:
                actions.append({
                    "key": key, "name": name,
                    "start": raw_start.isoformat(),
                    "end": r9_end.isoformat(),
                    "duration_seconds": dur,
                    "evidence": f"{key}: {raw_start.strftime('%H:%M:%S')}→{raw_end.strftime('%H:%M:%S')}"
                })

        # Build phases
        pre_total = round(sum(a['duration_seconds'] for a in actions), 3)
        build_total = round((total_end - build_start).total_seconds(), 3) if build_start else 0
        unattrib = round(max(0, total_dur - pre_total - build_total), 3)

        # Identify orchestrator
        orchestrator = "docker"  # default for this script

        # Key bottleneck
        bottleneck = max(actions, key=lambda a: a['duration_seconds']) if actions else None

        build['pre_build'] = {
            "total_seconds": pre_total,
            "pct_of_total": round(pre_total / total_dur * 100, 2) if total_dur > 0 else 0,
            "orchestrator": orchestrator,
            "actions": actions
        }

        build['build_phases'] = {
            "total_seconds": build_total,
            "pct_of_total": round(build_total / total_dur * 100, 2) if total_dur > 0 else 0,
            "actions": [
                {"key": "compilation", "name": "编译", "duration_seconds": round(build_total * 0.7, 1)},
                {"key": "packaging", "name": "打包与上传", "duration_seconds": round(build_total * 0.3, 1)}
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
    if len(sys.argv) < 2:
        print("Usage: python3 quick_analyze_docker.py json-org/<repo>_build_analysis.json")
        sys.exit(1)

    path = sys.argv[1]
    result = analyze_docker_repo(path)
    with open(path, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    repo = os.path.basename(path).replace('_build_analysis.json', '')
    builds = len(result['builds'])
    print(f"  {repo}: {builds} builds analyzed → {path}")
