#!/usr/bin/env python3
"""CI/CD Build Analysis Kanban Generator.

Reads all JSON files from json/, embeds data into template.html,
and outputs a self-contained index.html.
"""

import json
import glob
import os
from datetime import datetime


def load_all_data(json_dir="json"):
    """Load and merge all build analysis JSON files.

    Returns:
        list[dict]: Sorted list of repo data, each with:
            - All original meta fields
            - builds: list of build dicts
            - _filename: source filename
            - _has_error: bool, True if any build has _error
    """
    files = sorted(glob.glob(os.path.join(json_dir, "*.json")))
    repos = []
    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["_filename"] = os.path.basename(fpath)
        data["_has_error"] = any("_error" in b for b in data.get("builds", []))
        repos.append(data)

    # Sort: repos with errors first, then by build count descending
    repos.sort(key=lambda r: (not r["_has_error"], -len(r.get("builds", []))))
    return repos


def compute_derived_fields(repos):
    """Add computed fields to each repo and build for easier frontend rendering.

    Adds to each repo:
        - _repo_short: short repo name (e.g. "MindIE-LLM")
        - _total_builds: total build count
        - _passed_builds: count of passed builds
        - _failed_builds: count of failed builds
        - _max_fetched_at: latest fetched_at across builds

    Adds to each build:
        - _arch: "ARM" | "x86" | "unknown" derived from task_name
        - _pre_build_pct: pre_build.total_seconds / time.duration_seconds * 100
    """
    for repo in repos:
        builds = repo.get("builds", [])
        repo["_repo_short"] = repo["meta"]["repo"].split("/")[-1]
        repo["_total_builds"] = len(builds)
        repo["_passed_builds"] = sum(1 for b in builds if b.get("status") == "passed")
        repo["_failed_builds"] = sum(1 for b in builds if b.get("status") == "failed")
        repo["_max_fetched_at"] = repo["meta"].get("fetched_at", "")

        for build in builds:
            if "_error" in build:
                build["_arch"] = "unknown"
                build["_pre_build_pct"] = 0
                continue

            task_lower = build.get("task_name", "").lower()
            if "arm" in task_lower or "aarch" in task_lower:
                build["_arch"] = "ARM"
            elif "x86" in task_lower:
                build["_arch"] = "x86"
            else:
                build["_arch"] = "unknown"

            dur = build.get("time", {}).get("duration_seconds", 1)
            pre = build.get("pre_build", {}).get("total_seconds", 0)
            build["_pre_build_pct"] = round(pre / dur * 100, 1) if dur > 0 else 0

    return repos


def generate(repos):
    """Generate index.html from template and data."""
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    data_json = json.dumps(repos, ensure_ascii=False)
    html = template.replace("{{DATA_JSON}}", data_json)

    output_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    total_builds = sum(len(r.get("builds", [])) for r in repos)
    print(f"Generated index.html: {len(repos)} repos, {total_builds} builds → {output_path}")


if __name__ == "__main__":
    repos = load_all_data()
    repos = compute_derived_fields(repos)
    generate(repos)
