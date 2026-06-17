#!/usr/bin/env python3
"""Build log JSON normalizer.

Reads raw build analysis JSON files from json-org/, applies normalization
rules, and writes standardized output to json/.

Normalization rules:
1. key_bottleneck = name of the longest pre_build action (not build_phases)
2. key_bottleneck_seconds = duration of that action
3. unattributed_seconds = max(0, total - pre_build - build)
4. All original fields preserved unchanged
"""

import json
import glob
import os
import sys
from datetime import datetime


def normalize_build(build):
    """Normalize a single build entry in-place. Returns the modified build."""
    if "_error" in build:
        return build

    pre = build.get("pre_build", {})
    bp = build.get("build_phases", {})
    summary = build.get("summary", {})
    total = build.get("time", {}).get("duration_seconds", 0)

    # --- Rule 1&2: bottleneck from pre_build only ---
    actions = pre.get("actions", [])
    if actions:
        longest = max(actions, key=lambda a: a.get("duration_seconds", 0))
        summary["key_bottleneck"] = longest.get("name", "")
        summary["key_bottleneck_seconds"] = longest.get("duration_seconds", 0)
    else:
        summary["key_bottleneck"] = ""
        summary["key_bottleneck_seconds"] = 0

    # --- Rule 3: unattributed_seconds >= 0 ---
    pre_sec = summary.get("pre_build_seconds", pre.get("total_seconds", 0))
    build_sec = summary.get("build_seconds", bp.get("total_seconds", 0))
    if total > 0:
        unattributed = max(0, total - pre_sec - build_sec)
        summary["unattributed_seconds"] = round(unattributed, 1)

    # Update summary with actual pre_build/build totals
    summary["pre_build_seconds"] = round(pre.get("total_seconds", 0), 1)
    summary["build_seconds"] = round(bp.get("total_seconds", 0), 1)

    build["summary"] = summary
    return build


def normalize_file(src_path, dst_path):
    """Normalize a single JSON file."""
    with open(src_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for build in data.get("builds", []):
        normalize_build(build)

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def normalize_all(json_org_dir="json-org", json_dir="json"):
    """Normalize all JSON files from json-org/ to json/."""
    if not os.path.isdir(json_org_dir):
        print(f"Error: {json_org_dir}/ directory not found")
        sys.exit(1)

    files = sorted(glob.glob(os.path.join(json_org_dir, "*.json")))
    if not files:
        print(f"No JSON files found in {json_org_dir}/")
        return

    os.makedirs(json_dir, exist_ok=True)

    total_builds = 0
    total_fixed = 0
    for src in files:
        fname = os.path.basename(src)
        dst = os.path.join(json_dir, fname)

        # Check if existing output needs update
        need_update = True
        if os.path.exists(dst):
            src_mtime = os.path.getmtime(src)
            dst_mtime = os.path.getmtime(dst)
            if dst_mtime > src_mtime:
                print(f"  Skip {fname} (unchanged)")
                continue

        data = normalize_file(src, dst)
        builds = len(data.get("builds", []))
        total_builds += builds
        print(f"  Normalized {fname} → {builds} builds")

    print(f"\nDone: {len(files)} files, {total_builds} builds → {json_dir}/")


if __name__ == "__main__":
    json_org = sys.argv[1] if len(sys.argv) > 1 else "json-org"
    json_out = sys.argv[2] if len(sys.argv) > 2 else "json"
    normalize_all(json_org, json_out)
