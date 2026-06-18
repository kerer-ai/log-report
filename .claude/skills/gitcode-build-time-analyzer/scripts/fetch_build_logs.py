#!/usr/bin/env python3
"""
Fetch complete build-task logs from a GitCode PR pipeline for AI analysis.

This script does NOT analyze phase timing — it only fetches the raw log data
and extracts a representative sample suitable for AI semantic analysis.
The AI (Claude) reads the sampled log content and produces the structured
phase-breakdown JSON template defined in SKILL.md.
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta


CST = timezone(timedelta(hours=8))

# log timestamp: [2026/06/16 18:02:15.123 GMT+08:00]
TS_RE = re.compile(r"\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) GMT\+08:00\]")

SENSITIVE_PATTERNS = [
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(token=)[^&\s]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(signature=)[^&\s]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(cookie\s*:\s*)[^\r\n]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(ak|sk|secret|password|passwd)\b\s*[:=]\s*[^\s,;]+"), "[REDACTED_SECRET]"),
]

STATUS_MAP = {"9989": "passed", "10060": "failed", "128346": "running", "128721": "skipped"}
TEXT_STATUS_MAP = {
    "SUCCESS": "passed", "FAILED": "failed", "RUNNING": "running",
    "ABORTED": "aborted", "CANCELED": "canceled", "SKIPPED": "skipped",
    "UNSELECTED": "unselected",
}


# ── Helpers ───────────────────────────────────────────────────────────


def redact(text):
    for pat, repl in SENSITIVE_PATTERNS:
        text = pat.sub(repl, text)
    return text


def fetch_json(url, payload=None, method=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def run_gc_pr_comments(repo, pr):
    result = subprocess.run(
        ["gitcode", "pr", "comments", str(pr), "-R", repo],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout or ""


def parse_table_rows(table_html):
    rows = []
    if not table_html:
        return rows
    last_stage = ""
    tr_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S)
    for tr in tr_matches[1:]:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        if not cells:
            continue
        links = re.findall(r'href=["\']?([^"\' >]+)', tr)
        has_entity_status = any(re.search(r'&#\d+;', cell) for cell in cells)

        if has_entity_status:
            if len(cells) == 4:
                last_stage = re.sub(r"<.*?>", "", cells[0] or "").strip()
                task_raw, status_raw, detail_raw = cells[1], cells[2], cells[3]
            elif len(cells) == 3:
                task_raw, status_raw, detail_raw = cells
            else:
                continue
            status_code = (re.search(r'&#(\d+);', status_raw) or [None, ""])[1]
            task_name = re.sub(r"<.*?>", "", task_raw or "").strip()
            rows.append({
                "stage": last_stage, "task": task_name,
                "status": STATUS_MAP.get(status_code, "unknown"),
                "link": links[0] if links else "",
            })
        else:
            cleaned = [re.sub(r"<.*?>", "", c or "").strip() for c in cells]
            if len(cleaned) >= 2 and cleaned[0] and cleaned[0] != "任务名称":
                status_text = cleaned[1].replace("✅", "").replace("❌", "").strip().upper()
                rows.append({
                    "stage": last_stage, "task": cleaned[0],
                    "status": TEXT_STATUS_MAP.get(status_text, status_text.lower()),
                    "link": links[0] if links else "",
                })
    return rows


def parse_pipeline_comments(comments_text):
    blocks = []
    for comment in _split_comments(comments_text):
        if "流水线任务触发成功" in comment:
            link_match = re.search(
                r"https://www\.openlibing\.com/apps/pipelineDetail\?pipelineId=[^'\"\s<]+",
                comment,
            )
            if not link_match:
                continue
            table_match = re.search(r"(<table.*?</table>)", comment, re.S)
            table = table_match.group(1) if table_match else ""
            rows = parse_table_rows(table)
            ts_match = re.search(r"Author: .* at (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", comment)
            blocks.append({
                "name": "pipeline", "state": "triggered",
                "link": link_match.group(0), "rows": rows,
                "comment_time": ts_match.group(1) if ts_match else "",
            })
    if any(b.get("rows") for b in blocks):
        return blocks

    pattern = re.compile(
        r'流水线 <a href="(?P<link>[^"]+)">(?P<name>[^<]+)</a> (?P<state>[^<]+)</div>(?P<table>.*?</table>)',
        re.S,
    )
    for match in pattern.finditer(comments_text):
        rows = parse_table_rows(match.group("table"))
        blocks.append({
            "name": match.group("name"), "state": match.group("state"),
            "link": match.group("link"), "rows": rows,
            "comment_time": "",
        })
    return blocks


def _split_comments(text):
    if not text:
        return []
    blocks, current = [], []
    for line in text.splitlines():
        if line.startswith("#") and ") ID:" in line:
            if current:
                blocks.append("\n".join(current))
                current = []
        if line.strip() or current:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def choose_latest_block(blocks):
    if not blocks:
        return None
    blocks_with_rows = [b for b in blocks if b.get("rows")]
    if not blocks_with_rows:
        return None
    return blocks_with_rows[-1]


def extract_params(detail_link):
    query = urllib.parse.parse_qs(urllib.parse.urlparse(detail_link).query)
    params = {}
    for key in ["projectId", "pipelineId", "pipelineRunId", "jobRunId", "stepRunId"]:
        vals = query.get(key)
        if not vals:
            raise SystemExit(f"Missing {key} in task detail link")
        params[key] = vals[0]
    return params


def get_latest_merged_pr(repo):
    """Return the PR number of the most recently merged PR in the repo."""
    result = subprocess.run(
        ["gitcode", "pr", "list", "-R", repo, "--state", "merged", "-L", "1", "--json"],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    try:
        data = json.loads(result.stdout or "[]")
        if isinstance(data, list) and data:
            return int(data[0].get("number") or data[0].get("iid", 0))
        if isinstance(data, dict):
            items = data.get("data") or data.get("items") or data.get("list") or []
            if items:
                return int(items[0].get("number") or items[0].get("iid", 0))
    except (json.JSONDecodeError, ValueError, KeyError, IndexError):
        pass
    # Fallback: parse text output
    for line in (result.stdout or "").splitlines():
        m = re.match(r"#(\d+)\s+", line.strip())
        if m:
            return int(m.group(1))
    raise SystemExit(f"Could not find any merged PR in {repo}")
    payload = dict(params)
    payload.update({
        "sort": sort, "limit": limit,
        "startOffset": start_offset, "endOffset": end_offset,
    })
    req = urllib.request.Request(
        "https://www.openlibing.com/gateway/openlibing-cicd/project/pipeline/exec-log",
        data=json.dumps(payload).encode(),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8", "ignore"))
    if body.get("code") != 200:
        raise SystemExit(f"exec-log request failed: {body}")
    return body["data"]


def fetch_exec_log(params, sort="asc", limit=500, start_offset=0, end_offset=0):
    payload = dict(params)
    payload.update({
        "sort": sort, "limit": limit,
        "startOffset": start_offset, "endOffset": end_offset,
    })
    req = urllib.request.Request(
        "https://www.openlibing.com/gateway/openlibing-cicd/project/pipeline/exec-log",
        data=json.dumps(payload).encode(),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8", "ignore"))
    if body.get("code") != 200:
        raise SystemExit(f"exec-log request failed: {body}")
    return body["data"]


def fetch_all_logs(params, max_pages=60):
    """Fetch all log pages in ascending order, return concatenated raw text."""
    parts = []
    start_offset = 0
    end_offset = 0
    for _ in range(max_pages):
        data = fetch_exec_log(params, sort="asc", limit=500,
                              start_offset=start_offset, end_offset=end_offset)
        log = data.get("log", "")
        if log:
            parts.append(log)
        if not data.get("has_more"):
            break
        start_offset = data.get("start_offset", 0)
        end_offset = data.get("end_offset", 0)
    return "\n".join(parts)


def parse_timestamp(line):
    m = TS_RE.search(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=CST)
    except ValueError:
        return None


# ── Log sampling for AI analysis ─────────────────────────────────────


def sample_log_for_ai(full_log, max_sample_lines=400):
    """
    Extract a representative log sample suitable for AI semantic analysis.

    Strategy:
    - Always include the first 100 and last 50 timestamped lines.
    - Detect "significant gaps" (>3s between consecutive timestamped lines)
      and include 20 lines before/after each gap — these are likely phase
      boundaries.
    - Include the first occurrence of key semantic markers.
    - Ensure total sample is <= max_sample_lines.
    """
    lines = full_log.split("\n")
    entries = []
    for line in lines:
        ts = parse_timestamp(line)
        if ts:
            entries.append((ts, line))

    if not entries:
        return {"sample_log": "", "sample_line_count": 0, "total_lines": len(lines)}

    total = len(entries)
    first_ts = entries[0][0]
    last_ts = entries[-1][0]

    # Always include first N and last N
    head_count = min(100, total)
    tail_count = min(50, total - head_count)
    head = entries[:head_count]
    tail = entries[-tail_count:] if tail_count > 0 else []

    # Detect gaps >3s between consecutive lines
    gap_boundaries = set()
    for i in range(1, len(entries)):
        gap_s = (entries[i][0] - entries[i-1][0]).total_seconds()
        if gap_s > 3.0:
            # Lines around the gap
            before = range(max(0, i - 20), i)
            after = range(i, min(len(entries), i + 20))
            gap_boundaries.update(before)
            gap_boundaries.update(after)

    # Semantic marker lines (first occurrence of each category)
    MARKERS = [
        r"slave_create",
        r"代码检出",
        r"git\s+(?:clone|fetch|checkout|pull)",
        r"(?:pip|pip3)\s+install",
        r"apt(?:-get)?\s+install",
        r"cmake\s+",
        r"setup\.py\s+(?:build|develop|install|bdist)",
        r"running\s+(?:build_ext|build_py|egg_info|bdist_wheel)",
        r"gcc\s+|g\+\+\s+|cc\s+",
        r"ninja",
        r"make\[",
        r"\[.*%\].*(?:Built|Building)",
        r"Successfully\s+installed",
        r"auditwheel",
        r"Building\s+wheel",
    ]
    marker_indices = set()
    for i, (ts, line) in enumerate(entries):
        for pat in MARKERS:
            if re.search(pat, line, re.I):
                marker_indices.add(i)
                break

    # Collect sample indices
    sample_indices = set(range(head_count))
    if tail_count > 0:
        sample_indices.update(range(total - tail_count, total))
    sample_indices.update(gap_boundaries)
    sample_indices.update(marker_indices)

    # If too many, cap
    if len(sample_indices) > max_sample_lines:
        # Prioritize head, tail, and gap boundaries over marker lines
        priority = set(range(head_count)) | set(range(total - tail_count, total)) | gap_boundaries
        remaining = max_sample_lines - len(priority)
        extra_markers = sorted(marker_indices - priority)[:max(0, remaining)]
        sample_indices = priority | set(extra_markers)

    sample_indices = sorted(sample_indices)[:max_sample_lines]

    # Build sample log
    sample_lines = []
    prev_idx = -2
    for idx in sample_indices:
        if idx < len(entries):
            ts, line = entries[idx]
            # Add separator for gaps in sample
            if prev_idx >= 0 and idx - prev_idx > 5:
                sample_lines.append(f"... [skipped {idx - prev_idx - 1} lines] ...")
            sample_lines.append(redact(line))
            prev_idx = idx

    sample = "\n".join(sample_lines)

    # Build timestamp summary
    ts_summary = {
        "first": entries[0][0].isoformat(),
        "last": entries[-1][0].isoformat(),
        "duration_seconds": round((last_ts - first_ts).total_seconds(), 3),
        "total_timestamped_lines": total,
        "sample_lines_included": len(sample_indices),
    }

    # Detect significant timestamp gaps (for AI hint)
    significant_gaps = []
    for i in range(1, len(entries)):
        gap_s = (entries[i][0] - entries[i-1][0]).total_seconds()
        if gap_s > 5.0:
            significant_gaps.append({
                "after_line": i,
                "gap_seconds": round(gap_s, 3),
                "before_ts": entries[i-1][0].isoformat(),
                "after_ts": entries[i][0].isoformat(),
                "sample_before": redact(entries[i-1][1][:200]),
                "sample_after": redact(entries[i][1][:200]),
            })

    return {
        "sample_log": sample,
        "sample_line_count": len(sample_indices),
        "total_lines_in_log": total,
        "raw_log_total_chars": len(full_log),
        "timestamp_summary": ts_summary,
        "significant_gaps": significant_gaps[:30],  # cap
    }


# ── Main ──────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Fetch build-task logs from GitCode PR pipeline for AI analysis"
    )
    parser.add_argument("--repo", required=True, help="owner/repo, e.g. Ascend/pytorch")
    parser.add_argument("--pr", type=int, help="PR number (omit if using --latest-merged)")
    parser.add_argument("--latest-merged", action="store_true",
                        help="Auto-discover the most recent merged PR in the repo")
    parser.add_argument("--task", help="Specific build task name (default: all passed builds)")
    parser.add_argument("--max-sample", type=int, default=400,
                        help="Max log sample lines for AI (default: 400)")
    parser.add_argument("--full-log", action="store_true",
                        help="Output the full raw log (warning: can be very large)")
    parser.add_argument("--output", "-o",
                        help="Output JSON file path (default: builds_<repo>_pr<number>.json)")
    args = parser.parse_args()

    # Resolve PR number
    if args.latest_merged:
        pr_number = get_latest_merged_pr(args.repo)
        print(f"Latest merged PR: #{pr_number}", file=sys.stderr)
    elif args.pr:
        pr_number = args.pr
    else:
        parser.error("Either --pr or --latest-merged must be specified")

    # 1. Fetch and parse PR pipeline comments
    comments = run_gc_pr_comments(args.repo, pr_number)
    blocks = parse_pipeline_comments(comments)
    if not blocks:
        print(json.dumps({"error": "No pipeline table found in PR comments"}, ensure_ascii=False))
        sys.exit(0)

    # 2. Find passed build tasks — aggregate from ALL pipeline blocks
    all_rows = []
    for block in blocks:
        if block.get("rows"):
            all_rows.extend(block["rows"])
    pipeline_url = blocks[0].get("link", "")
    build_tasks = [
        r for r in all_rows
        if r["status"] == "passed"
        and ("build" in r["task"].lower() or "compile" in r["task"].lower() or r.get("stage", "") == "编译构建")
    ]
    if args.task:
        build_tasks = [t for t in build_tasks if t["task"] == args.task]
        if not build_tasks:
            build_tasks = [t for t in block["rows"] if t["task"] == args.task and t["status"] == "passed"]
    if not build_tasks:
        print(json.dumps({"error": "No passed build tasks found"}, ensure_ascii=False))
        sys.exit(0)

    # 3. Fetch log for each build task
    builds = []
    for task in build_tasks:
        task_name = task["task"]
        print(f"Fetching log for {task_name} ...", file=sys.stderr)

        try:
            params = extract_params(task["link"])
        except SystemExit:
            builds.append({
                "task_name": task_name,
                "error": "Cannot extract API params from task link",
            })
            continue

        try:
            full_log = fetch_all_logs(params)
        except Exception as e:
            builds.append({
                "task_name": task_name,
                "error": f"Failed to fetch log: {e}",
            })
            continue

        # Parse first/last timestamps
        lines = full_log.split("\n")
        first_ts = None
        last_ts = None
        for line in lines:
            ts = parse_timestamp(line)
            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

        build_entry = {
            "task_name": task_name,
            "stage": task.get("stage", ""),
            "status": task["status"],
            "detail_url": task.get("link", ""),
        }

        if first_ts:
            build_entry["time"] = {
                "start": first_ts.isoformat(),
                "end": last_ts.isoformat(),
                "duration_seconds": round((last_ts - first_ts).total_seconds(), 3),
            }

        if args.full_log:
            build_entry["full_log"] = redact(full_log[:200000])  # cap at 200k chars
        else:
            sample = sample_log_for_ai(full_log, args.max_sample)
            build_entry["log_sample"] = sample["sample_log"]
            build_entry["log_stats"] = {
                "total_timestamped_lines": sample["total_lines_in_log"],
                "sample_lines": sample["sample_line_count"],
                "raw_chars": sample["raw_log_total_chars"],
            }
            build_entry["timestamp_summary"] = sample["timestamp_summary"]
            build_entry["significant_gaps"] = sample["significant_gaps"]

        builds.append(build_entry)

    # 4. Build standardized output template with empty pre_build/build slots for AI
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    import copy
    now = _dt.now(_tz(_td(hours=8))).isoformat()

    pr_url = f"https://gitcode.com/{args.repo}/pull/{pr_number}"

    PRE_BUILD_TEMPLATE = {
        "total_seconds": 0,
        "pct_of_total": 0,
        "orchestrator": "",
        "actions": [
            {"key": "node_assignment",       "name": "执行节点分配",          "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "docker_pull",           "name": "Docker 镜像拉取",       "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "cache_check",           "name": "缓存检查",              "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "git_checkout",          "name": "代码检出",              "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "git_checkout_pod",      "name": "代码检出 (Pod内)",      "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "network_retry",         "name": "网络重试等待",          "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "workspace_prep",        "name": "工作目录准备",          "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "pre_submit_validation", "name": "前置校验",              "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "image_proxy",           "name": "镜像代理替换",          "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "git_cache_injection",   "name": "Git 缓存注入",         "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "orchestrator_submit",   "name": "编排器任务提交",        "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "pod_scheduling",        "name": "Pod 调度等待",          "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "artifact_download",     "name": "制品/依赖包下载",       "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "tool_download",         "name": "构建工具下载",          "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "pip_install",           "name": "Python 依赖安装",       "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "conda_install",         "name": "Conda 依赖安装",        "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "apt_install",           "name": "系统包安装",            "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
            {"key": "env_setup",             "name": "环境变量设置",          "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
        ]
    }

    BUILD_PHASES_TEMPLATE = {
        "total_seconds": 0,
        "pct_of_total": 0,
        "actions": [
            {"key": "cmake_configure", "name": "CMake 配置",      "duration_seconds": 0},
            {"key": "compilation",     "name": "编译",            "duration_seconds": 0},
            {"key": "packaging",       "name": "打包与上传",      "duration_seconds": 0},
        ]
    }

    for b in builds:
        if "error" in b:
            # R2: Error records get empty-but-valid structure + _error marker
            b["_error"] = b.pop("error")
            b.setdefault("time", None)
            b["pre_build"] = {"total_seconds": 0, "pct_of_total": 0, "orchestrator": "", "actions": []}
            b["build_phases"] = {"total_seconds": 0, "pct_of_total": 0, "actions": []}
            b["summary"] = {"pre_build_seconds": 0, "build_seconds": 0, "unattributed_seconds": 0, "key_bottleneck": "", "key_bottleneck_seconds": 0}
        else:
            if "pre_build" not in b:
                b["pre_build"] = copy.deepcopy(PRE_BUILD_TEMPLATE)
            if "build_phases" not in b:
                b["build_phases"] = copy.deepcopy(BUILD_PHASES_TEMPLATE)
            if "summary" not in b:
                b["summary"] = {"pre_build_seconds": 0, "build_seconds": 0, "unattributed_seconds": 0, "key_bottleneck": "", "key_bottleneck_seconds": 0}

    # R3: Deduplicate builds by task_name, keep latest by time.start
    deduped = {}
    for b in builds:
        name = b["task_name"]
        t = b.get("time") or {}
        start = t.get("start", "") if isinstance(t, dict) else ""
        if name not in deduped or (start and start > (deduped[name].get("time") or {}).get("start", "")):
            deduped[name] = b
    builds = list(deduped.values())

    pipeline_meta = blocks[0] if blocks else {}
    result = {
        "meta": {
            "pr": pr_number,
            "repo": args.repo,
            "pr_url": pr_url,
            "pipeline_name": pipeline_meta.get("name", ""),
            "pipeline_state": pipeline_meta.get("state", ""),
            "pipeline_url": pipeline_url,
            "comment_time": pipeline_meta.get("comment_time", ""),
            "fetched_at": now,
            "analyzed_at": None,
            "analysis_method": "ai_semantic",
        },
        "builds": builds,
    }

    # Determine output path
    output_path = args.output
    if not output_path:
        safe_repo = args.repo.replace("/", "_")
        output_path = f"builds_{safe_repo}_pr{pr_number}.json"

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    # Summary to stderr, status to stdout
    print(f"Template written to: {output_path}", file=sys.stderr)
    print(json.dumps({"status": "ok", "output_file": output_path, "pr": pr_number, "build_count": len(builds)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
