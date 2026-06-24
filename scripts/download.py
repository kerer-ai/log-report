#!/usr/bin/env python3
"""
Download raw CI build logs from openlibing or Jenkins backends.

Reads a task manifest (Stage 1 AI output) from json-org/<repo>_manifest.json,
downloads raw logs, saves to logs/<repo>/pr<NNN>/<task>-<timestamp>.log.gz,
and generates json-org/<repo>_build_analysis.json with log_file paths.

Usage:
    python3 scripts/download.py --manifest json-org/kernel_manifest.json
    python3 scripts/download.py --manifest json-org/pytorch_manifest.json --output json-org/pytorch_build_analysis.json
"""

import argparse
import copy
import gzip
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

# ── Timestamp parsers ────────────────────────────────────────────────

# openlibing: [2026/06/16 18:02:15.123 GMT+08:00]
TS_RE = re.compile(r"\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) GMT\+08:00\]")

# Jenkins: [2026-06-22 10:35:24]
JENKINS_TS_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")


def parse_timestamp(line):
    m = TS_RE.search(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=CST)
    except ValueError:
        return None


def parse_jenkins_timestamp(line):
    m = JENKINS_TS_RE.search(line)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=CST)
    except ValueError:
        return None


# ── Sensitive data redaction ─────────────────────────────────────────

SENSITIVE_PATTERNS = [
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(token=)[^&\s]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(signature=)[^&\s]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(cookie\s*:\s*)[^\r\n]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(ak|sk|secret|password|passwd)\b\s*[:=]\s*[^\s,;]+"), "[REDACTED_SECRET]"),
]


def redact(text):
    for pat, repl in SENSITIVE_PATTERNS:
        text = pat.sub(repl, text)
    return text


# ── HTTP helpers ──────────────────────────────────────────────────────

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


def http_get_text(url, timeout=60):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain, */*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


# ── openlibing log download ───────────────────────────────────────────

def extract_params(detail_link):
    query = urllib.parse.parse_qs(urllib.parse.urlparse(detail_link).query)
    params = {}
    for key in ["projectId", "pipelineId", "pipelineRunId", "jobRunId", "stepRunId"]:
        vals = query.get(key)
        if not vals:
            raise SystemExit(f"Missing {key} in task detail link: {detail_link}")
        params[key] = vals[0]
    return params


def fetch_exec_log(params, sort="asc", limit=500, start_offset=0, end_offset=0):
    payload = dict(params)
    payload.update({
        "sort": sort, "limit": limit,
        "startOffset": start_offset, "endOffset": end_offset,
    })
    url = "https://www.openlibing.com/gateway/openlibing-cicd/project/pipeline/exec-log"
    req = urllib.request.Request(
        url,
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


# ── Jenkins log download ──────────────────────────────────────────────

def fetch_jenkins_build_info(console_url):
    api_url = console_url.rstrip("/")
    if api_url.endswith("/console"):
        api_url = api_url[:-len("/console")]
    api_url += "/api/json"
    return fetch_json(api_url)


def fetch_jenkins_console_text(console_url):
    text_url = console_url.rstrip("/")
    if not text_url.endswith("/consoleText"):
        if text_url.endswith("/console"):
            text_url = text_url[:-len("/console")] + "/consoleText"
        else:
            text_url += "/consoleText"
    return http_get_text(text_url, timeout=60)


# ── Helpers ───────────────────────────────────────────────────────────

def slugify(name):
    """Make a task name safe for filenames."""
    s = re.sub(r'[^\w\-_.]', '_', name)
    s = re.sub(r'_+', '_', s)
    return s[:200]


def now_cst():
    return datetime.now(CST).isoformat()


def load_template(schema_path="schema/template.json"):
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download raw CI build logs from openlibing or Jenkins"
    )
    parser.add_argument("--manifest", required=True,
                        help="Path to manifest JSON (Stage 1 AI output)")
    parser.add_argument("--output", "-o",
                        help="Output build analysis JSON path (default: json-org/<repo>_build_analysis.json)")
    parser.add_argument("--schema", default="schema/template.json",
                        help="Path to schema/template.json")
    args = parser.parse_args()

    # Load manifest
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    repo = manifest["repo"]
    pr = manifest["pr"]
    ci_backend = manifest.get("ci_backend", "openlibing")
    pr_url = manifest.get("pr_url", f"https://gitcode.com/{repo}/pull/{pr}")
    pipeline_url = manifest.get("pipeline_url", "")
    repo_name = repo.split("/")[-1]

    # Load schema for template
    schema = load_template(args.schema)
    catalog = schema["action_catalog"].get(ci_backend, schema["action_catalog"]["openlibing"])

    # Set up log directory
    log_dir = os.path.join("logs", repo_name, f"pr{pr}")
    os.makedirs(log_dir, exist_ok=True)

    print(f"Repo: {repo}  PR: #{pr}  Backend: {ci_backend}", file=sys.stderr)
    print(f"Log dir: {log_dir}", file=sys.stderr)

    builds = []
    for task in manifest.get("tasks", []):
        task_name = task["task_name"]
        status = task.get("status", "passed")
        detail_url = task.get("detail_url", "")

        print(f"  Downloading: {task_name} ...", file=sys.stderr)

        build_entry = {
            "task_name": task_name,
            "stage": task.get("stage", ""),
            "status": status,
            "detail_url": detail_url,
            "log_file": "",
            "pre_build": {
                "total_seconds": 0,
                "pct_of_total": 0,
                "orchestrator": "jenkins" if ci_backend == "jenkins" else "",
                "actions": copy.deepcopy(catalog["pre_build"]),
            },
            "build_phases": {
                "total_seconds": 0,
                "pct_of_total": 0,
                "actions": copy.deepcopy(catalog["build_phases"]),
            },
            "summary": {
                "pre_build_seconds": 0, "build_seconds": 0,
                "unattributed_seconds": 0, "key_bottleneck": "", "key_bottleneck_seconds": 0,
            },
        }

        try:
            if ci_backend == "jenkins":
                # Jenkins: GET /api/json + GET /consoleText
                build_meta = fetch_jenkins_build_info(detail_url)
                full_log = fetch_jenkins_console_text(detail_url)

                start_ms = build_meta.get("timestamp")
                duration_ms = build_meta.get("duration")
                if start_ms and duration_ms:
                    start_dt = datetime.fromtimestamp(start_ms / 1000, tz=CST)
                    end_dt = datetime.fromtimestamp((start_ms + duration_ms) / 1000, tz=CST)
                    ts_str = start_dt.strftime("%Y-%m-%dT%H%M%S")
                    build_entry["time"] = {
                        "start": start_dt.isoformat(),
                        "end": end_dt.isoformat(),
                        "duration_seconds": round(duration_ms / 1000, 3),
                    }
                else:
                    ts_str = "unknown"
                    build_entry["time"] = None

                # Check for timestamped lines
                has_timestamps = False
                for line in full_log.split("\n")[:500]:
                    if parse_jenkins_timestamp(line):
                        has_timestamps = True
                        break

                # Save log
                task_slug = slugify(task_name)
                log_name = f"{task_slug}-{ts_str}.log.gz"
                log_path = os.path.join(log_dir, log_name)
                with gzip.open(log_path, "wt", encoding="utf-8", errors="replace") as f:
                    f.write(redact(full_log))
                build_entry["log_file"] = os.path.relpath(log_path)
                print(f"    → {log_path} ({len(full_log)} chars)", file=sys.stderr)

            else:
                # openlibing: extract API params + paginated fetch
                params = extract_params(detail_url)
                full_log = fetch_all_logs(params)

                # Parse first/last timestamps
                first_ts = None
                last_ts = None
                for line in full_log.split("\n"):
                    ts = parse_timestamp(line)
                    if ts:
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts

                if first_ts:
                    ts_str = first_ts.strftime("%Y-%m-%dT%H%M%S")
                    build_entry["time"] = {
                        "start": first_ts.isoformat(),
                        "end": last_ts.isoformat(),
                        "duration_seconds": round((last_ts - first_ts).total_seconds(), 3),
                    }
                else:
                    ts_str = "unknown"
                    build_entry["time"] = None

                # Save log
                task_slug = slugify(task_name)
                log_name = f"{task_slug}-{ts_str}.log.gz"
                log_path = os.path.join(log_dir, log_name)
                with gzip.open(log_path, "wt", encoding="utf-8", errors="replace") as f:
                    f.write(redact(full_log))
                build_entry["log_file"] = os.path.relpath(log_path)
                print(f"    → {log_path} ({len(full_log)} chars)", file=sys.stderr)

        except Exception as e:
            build_entry["_error"] = f"Download failed: {e}"
            build_entry["pre_build"] = {"total_seconds": 0, "pct_of_total": 0, "orchestrator": "", "actions": []}
            build_entry["build_phases"] = {"total_seconds": 0, "pct_of_total": 0, "actions": []}
            print(f"    ERROR: {e}", file=sys.stderr)

        builds.append(build_entry)

    # Deduplicate by task_name, keeping latest by time.start
    deduped = {}
    for b in builds:
        name = b["task_name"]
        t = b.get("time") or {}
        start = t.get("start", "") if isinstance(t, dict) else ""
        if name not in deduped or (start and start > (deduped[name].get("time") or {}).get("start", "")):
            deduped[name] = b
    builds = list(deduped.values())

    # Build output
    result = {
        "meta": {
            "pr": pr,
            "repo": repo,
            "pr_url": pr_url,
            "pipeline_name": manifest.get("pipeline_name", ""),
            "pipeline_state": manifest.get("pipeline_state", ""),
            "pipeline_url": pipeline_url,
            "comment_time": manifest.get("comment_time", ""),
            "fetched_at": now_cst(),
            "analyzed_at": None,
            "analysis_method": "ai_semantic",
        },
        "builds": builds,
    }

    # Write output
    output_path = args.output or os.path.join("json-org", f"{repo_name}_build_analysis.json")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    ok = sum(1 for b in builds if "_error" not in b)
    err = sum(1 for b in builds if "_error" in b)
    print(f"Done: {ok} downloaded, {err} errors → {output_path}", file=sys.stderr)
    print(json.dumps({"status": "ok", "output_file": output_path,
                       "build_count": len(builds), "ok": ok, "errors": err},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
