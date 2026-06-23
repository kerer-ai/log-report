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

# ── Jenkins-specific constants ─────────────────────────────────────────

JENKINS_STATUS_MAP = {
    "9989": "passed",   # &#9989; = ✅ SUCCESS
    "10060": "failed",  # &#10060; = ❌ FAILED
    "9888": "warning",  # &#9888; = ⚠️ WARNING
}

# Jenkins console log timestamp: [2026-06-22 10:35:24]
JENKINS_TS_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")

# Jenkins PR identification in log: "PR 24093 [user:branch -> target_branch]"
JENKINS_PR_RE = re.compile(r"PR (\d+) \[([^:]+):([^\]]+)\s*->\s*([^\]]+)\]")

# openEuler Jenkins URL pattern
JENKINS_URL_RE = re.compile(
    r"https://ci\.openeuler\.openatom\.cn/job/multiarch/job/openeuler/job/"
    r"([a-z_0-9]+)/job/kernel/(\d+)/?console"
)

# Jenkins build phases to identify in logs (for sampling)
JENKINS_MARKERS = [
    r"\*\*\*\*\* clone check scripts \*\*\*\*\*",
    r"\*\*\*\*\* Start to download kernel of openeuler \*\*\*\*\*",
    r"\*\*\*\*\* Start to install build tools \*\*\*\*\*",
    r"\*\*\*\*\* Download and Apply PR \*\*\*\*\*",
    r"\*\*\*\*\* Build kernel with allmodconfig \*\*\*\*\*",
    r"\*\*\*\*\* Build kernel with openeuler_defconfig \*\*\*\*\*",
    r"\*\*\*\*\* Check kabi compatibility \*\*\*\*\*",
    r"\*\*\*\*\* Check openeuler_defconfig \*\*\*\*\*",
    r"\[  INFO \] .* pass\b",
    r"Finished: (?:SUCCESS|FAILURE)",
    r"PR \d+ ",
    r"make\[",
    r"(?:error|Error|ERROR):",
    r"CC\s+",
    r"HOSTCC\s+",
    r"LD\s+",
]

# Jenkins pre_build action template
JENKINS_PRE_BUILD_ACTIONS = [
    {"key": "clone_check_scripts",  "name": "Clone 检查脚本",       "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
    {"key": "clone_kernel_repo",    "name": "Clone 内核仓库",        "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
    {"key": "install_build_tools",  "name": "安装构建工具",          "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
    {"key": "apply_pr_patch",       "name": "应用 PR 补丁",          "start": None, "end": None, "duration_seconds": 0, "evidence": ""},
]

# Jenkins build_phases action template
JENKINS_BUILD_PHASES_ACTIONS = [
    {"key": "allmodconfig_build",  "name": "Allmodconfig 构建",     "duration_seconds": 0},
    {"key": "defconfig_build",     "name": "Defconfig 构建",         "duration_seconds": 0},
    {"key": "kabi_check",          "name": "KABI 兼容性检查",         "duration_seconds": 0},
    {"key": "defconfig_check",     "name": "Defconfig 一致性检查",    "duration_seconds": 0},
]

# Architecture display names
JENKINS_ARCH_NAMES = {
    "aarch64": "ARM64", "x86_64": "x86_64", "ppc": "PPC",
    "ppc64": "PPC64", "loongarch": "LoongArch", "arm": "ARM",
    "riscv64": "RISC-V 64",
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


def parse_openlibing_comments(comments_text):
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


def parse_pipeline_comments(comments_text, ci_backend="openlibing"):
    """Dispatch to backend-specific comment parser."""
    if ci_backend == "jenkins":
        return parse_jenkins_comments(comments_text)
    else:
        return parse_openlibing_comments(comments_text)


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
        return {"sample_log": "", "sample_line_count": 0, "total_lines_in_log": len(lines),
                "raw_log_total_chars": len(full_log), "timestamp_summary": {},
                "significant_gaps": []}

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


# ── Jenkins backend ────────────────────────────────────────────────────


def parse_jenkins_timestamp(line):
    """Parse Jenkins console timestamp: [2026-06-22 10:35:24] → datetime (CST)."""
    m = JENKINS_TS_RE.search(line)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=CST)
    except ValueError:
        return None


def jenkins_sample_log(full_log, max_sample_lines=400):
    """Extract a representative log sample from Jenkins console text.

    Same strategy as sample_log_for_ai(): head + tail + gap boundaries + markers.
    """
    lines = full_log.split("\n")
    entries = []
    for line in lines:
        ts = parse_jenkins_timestamp(line)
        if ts:
            entries.append((ts, line))

    if not entries:
        return {"sample_log": "", "sample_line_count": 0, "total_lines_in_log": len(lines),
                "raw_log_total_chars": len(full_log), "timestamp_summary": {},
                "significant_gaps": []}

    total = len(entries)
    first_ts = entries[0][0]
    last_ts = entries[-1][0]

    head_count = min(100, total)
    tail_count = min(50, total - head_count)

    # Detect gaps >3s
    gap_boundaries = set()
    for i in range(1, len(entries)):
        gap_s = (entries[i][0] - entries[i - 1][0]).total_seconds()
        if gap_s > 3.0:
            gap_boundaries.update(range(max(0, i - 20), i))
            gap_boundaries.update(range(i, min(len(entries), i + 20)))

    # Marker lines
    marker_indices = set()
    for i, (ts, line) in enumerate(entries):
        for pat in JENKINS_MARKERS:
            if re.search(pat, line, re.I):
                marker_indices.add(i)
                break

    sample_indices = set(range(head_count))
    if tail_count > 0:
        sample_indices.update(range(total - tail_count, total))
    sample_indices.update(gap_boundaries)
    sample_indices.update(marker_indices)

    if len(sample_indices) > max_sample_lines:
        priority = set(range(head_count)) | set(range(total - tail_count, total)) | gap_boundaries
        remaining = max_sample_lines - len(priority)
        extra_markers = sorted(marker_indices - priority)[:max(0, remaining)]
        sample_indices = priority | set(extra_markers)

    sample_indices = sorted(sample_indices)[:max_sample_lines]

    sample_lines = []
    prev_idx = -2
    for idx in sample_indices:
        if idx < len(entries):
            ts, line = entries[idx]
            if prev_idx >= 0 and idx - prev_idx > 5:
                sample_lines.append(f"... [skipped {idx - prev_idx - 1} lines] ...")
            sample_lines.append(redact(line))
            prev_idx = idx

    sample = "\n".join(sample_lines)

    ts_summary = {
        "first": entries[0][0].isoformat(),
        "last": entries[-1][0].isoformat(),
        "duration_seconds": round((last_ts - first_ts).total_seconds(), 3),
        "total_timestamped_lines": total,
        "sample_lines_included": len(sample_indices),
    }

    significant_gaps = []
    for i in range(1, len(entries)):
        gap_s = (entries[i][0] - entries[i - 1][0]).total_seconds()
        if gap_s > 5.0:
            significant_gaps.append({
                "after_line": i,
                "gap_seconds": round(gap_s, 3),
                "before_ts": entries[i - 1][0].isoformat(),
                "after_ts": entries[i][0].isoformat(),
                "sample_before": redact(entries[i - 1][1][:200]),
                "sample_after": redact(entries[i][1][:200]),
            })

    return {
        "sample_log": sample,
        "sample_line_count": len(sample_indices),
        "total_lines_in_log": total,
        "raw_log_total_chars": len(full_log),
        "timestamp_summary": ts_summary,
        "significant_gaps": significant_gaps[:30],
    }


def parse_jenkins_table_rows(table_html):
    """Parse openeuler-ci-bot HTML table rows for Jenkins build/check results.

    Handles two table formats:
    - Static checks: Check Name | Check Result | Check Details (6 checks sharing one link)
    - Multi-arch builds: Check Name (colspan=2) | Build Result | Build Details
    """
    rows = []
    if not table_html:
        return rows

    tr_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S)
    # Skip header row
    for tr in tr_matches[1:]:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        if not cells:
            continue

        links = re.findall(r'href=["\']?([^"\' >]+)', tr)

        # Check for entity status codes (&#9989; etc.)
        status_raw = ""
        has_entity = False
        for cell in cells:
            m = re.search(r'&#(\d+);', cell)
            if m:
                has_entity = True
                status_raw = cell
                break

        if has_entity:
            status_code = (re.search(r'&#(\d+);', status_raw) or [None, ""])[1]
            status = JENKINS_STATUS_MAP.get(status_code, "unknown")

            cleaned = [re.sub(r"<.*?>", "", c or "").strip() for c in cells]

            if len(cleaned) == 4:
                # Format: stage | task | status | detail (4-column table)
                stage = cleaned[0]
                task_name = cleaned[1]
                detail_link = links[0] if links else ""
            elif len(cleaned) == 3:
                # Format: task | status | detail (3-column table)
                stage = ""
                task_name = cleaned[0]
                detail_link = links[0] if links else ""
            elif len(cleaned) == 2:
                # Format: task | status (no link — static checks share a link via rowspan)
                stage = ""
                task_name = cleaned[0]
                detail_link = links[0] if links else ""
            else:
                continue

            # Filter out non-build checks
            _tl = task_name.lower()
            if _tl in ("check_package_license", "checkpatch", "checkformat",
                        "checkdepend", "checkkabi", "checkconflict", "checkbinary",
                        "antipoison", "codecheck", "sca"):
                # Skip static analysis / license checks — not build tasks
                continue

            # Only keep check_build tasks — use arch name as task name
            if "check_build" in _tl or task_name in JENKINS_ARCH_NAMES:
                # For 4-column tables, stage is the arch name (e.g., "aarch64")
                # For 3-column tables, task_name is the arch
                arch = stage if stage not in ("", "编译构建") else task_name
                display_name = JENKINS_ARCH_NAMES.get(arch, arch)
                rows.append({
                    "stage": "编译构建",
                    "task": f"{display_name} (check_build)",
                    "status": status,
                    "link": detail_link,
                })
        else:
            # Text status format (backup path)
            cleaned = [re.sub(r"<.*?>", "", c or "").strip() for c in cells]
            if len(cleaned) >= 2 and cleaned[0]:
                status_text = re.sub(r"&#\d+;", "", cleaned[1]).strip().upper()
                task_name = cleaned[0].lower()
                if task_name in ("check_package_license", "checkpatch", "checkformat",
                                 "checkdepend", "checkkabi", "checkconflict", "checkbinary"):
                    continue
                rows.append({
                    "stage": "",
                    "task": cleaned[0],
                    "status": TEXT_STATUS_MAP.get(status_text, status_text.lower()),
                    "link": links[0] if links else "",
                })

    return rows


def parse_jenkins_comments(comments_text):
    """Parse openeuler-ci-bot Jenkins CI comments from a GitCode PR.

    Extracts multi-architecture build results (Type C comments).
    Filters out static check comments (Type B) and trigger comments (Type A).
    """
    blocks = []
    for comment in _split_comments(comments_text):
        if "ci.openeuler.openatom.cn" not in comment:
            continue

        table_match = re.search(r"(<table.*?</table>)", comment, re.S)
        if not table_match:
            continue

        table_html = table_match.group(1)
        rows = parse_jenkins_table_rows(table_html)
        if not rows:
            continue

        # Extract console links
        links = re.findall(
            r'https://ci\.openeuler\.openatom\.cn/job/multiarch/job/openeuler/job/'
            r'(?:aarch64|x86_64|ppc|ppc64|loongarch|arm|riscv64)/'
            r'job/kernel/\d+/?console',
            comment
        )
        ts_match = re.search(r"Author: .* at (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", comment)

        blocks.append({
            "name": "jenkins_pipeline",
            "state": "completed",
            "link": links[0] if links else "",
            "rows": rows,
            "comment_time": ts_match.group(1) if ts_match else "",
        })

    return blocks


def fetch_jenkins_build_info(console_url):
    """Fetch build metadata from Jenkins /api/json endpoint.

    Returns dict with keys: result, timestamp (ms epoch), duration (ms),
    estimatedDuration, building, id, url.
    """
    api_url = console_url.rstrip("/")
    if api_url.endswith("/console"):
        api_url = api_url[:-len("/console")]
    api_url += "/api/json"

    data = fetch_json(api_url)
    return data


def fetch_jenkins_console_text(console_url):
    """Fetch raw console text from Jenkins /consoleText endpoint."""
    text_url = console_url.rstrip("/")
    if not text_url.endswith("/consoleText"):
        if text_url.endswith("/console"):
            text_url = text_url[:-len("/console")] + "/consoleText"
        else:
            text_url += "/consoleText"

    req = urllib.request.Request(
        text_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "ignore")


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
    parser.add_argument("--ci-backend", choices=["openlibing", "jenkins"],
                        default="openlibing",
                        help="CI backend type (default: openlibing)")
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
    blocks = parse_pipeline_comments(comments, args.ci_backend)
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

        if args.ci_backend == "jenkins":
            # ── Jenkins path: single HTTP GET to /consoleText + /api/json ──
            try:
                build_meta = fetch_jenkins_build_info(task["link"])
                full_log = fetch_jenkins_console_text(task["link"])
            except Exception as e:
                builds.append({
                    "task_name": task_name,
                    "error": f"Jenkins fetch failed: {e}",
                })
                continue

            build_entry = {
                "task_name": task_name,
                "stage": task.get("stage", ""),
                "status": task["status"],
                "detail_url": task.get("link", ""),
            }

            # Use API timestamps for time.start/end
            start_ms = build_meta.get("timestamp")
            duration_ms = build_meta.get("duration")
            if start_ms and duration_ms:
                start_dt = datetime.fromtimestamp(start_ms / 1000, tz=CST)
                end_dt = datetime.fromtimestamp((start_ms + duration_ms) / 1000, tz=CST)
                build_entry["time"] = {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                    "duration_seconds": round(duration_ms / 1000, 3),
                }

            if args.full_log:
                build_entry["full_log"] = redact(full_log[:200000])
            else:
                sample = jenkins_sample_log(full_log, args.max_sample)
                build_entry["log_sample"] = sample["sample_log"]
                build_entry["log_stats"] = {
                    "total_timestamped_lines": sample["total_lines_in_log"],
                    "sample_lines": sample["sample_line_count"],
                    "raw_chars": sample["raw_log_total_chars"],
                }
                build_entry["timestamp_summary"] = sample["timestamp_summary"]
                build_entry["significant_gaps"] = sample["significant_gaps"]

        else:
            # ── openLiBing path (existing) ──
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
                build_entry["full_log"] = redact(full_log[:200000])
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
                if args.ci_backend == "jenkins":
                    b["pre_build"] = {
                        "total_seconds": 0,
                        "pct_of_total": 0,
                        "orchestrator": "jenkins",
                        "actions": copy.deepcopy(JENKINS_PRE_BUILD_ACTIONS),
                    }
                else:
                    b["pre_build"] = copy.deepcopy(PRE_BUILD_TEMPLATE)
            if "build_phases" not in b:
                if args.ci_backend == "jenkins":
                    b["build_phases"] = {
                        "total_seconds": 0,
                        "pct_of_total": 0,
                        "actions": copy.deepcopy(JENKINS_BUILD_PHASES_ACTIONS),
                    }
                else:
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
