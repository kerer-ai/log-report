#!/usr/bin/env python3
"""Validate build analysis JSON against R1-R9 quality rules.

Usage: python3 validate.py <json-file>
Exit code 0 = all checks pass, 1 = issues found.
"""

import json
import sys


def validate_build(b, idx):
    """Validate a single build entry. Returns list of error strings."""
    errors = []
    name = b.get("task_name", f"build_{idx}")

    if b.get("_error"):
        print(f"  {name}: SKIPPED (_error={b['_error']})")
        return errors

    pb = b.get("pre_build", {})
    bp = b.get("build_phases", {})
    s = b.get("summary", {})
    t = b.get("time", {})
    total = t.get("duration_seconds", 0)

    pre = pb.get("total_seconds", pb.get("seconds", 0))
    bld = bp.get("total_seconds", 0) if isinstance(bp, dict) else sum(
        a.get("duration_seconds", 0) for a in bp
    )
    unatt = s.get("unattributed_seconds", -1)

    # R6: summary consistency
    r6 = abs(pre + bld + unatt - total)
    if r6 >= 1.0:
        errors.append(
            f"{name}: R6 FAIL — pre={pre:.1f}+build={bld:.1f}+unatt={unatt:.1f}"
            f"={pre + bld + unatt:.1f} vs total={total:.1f}"
        )

    # Schema checks
    if isinstance(bp, list):
        errors.append(f"{name}: SCHEMA FAIL — build_phases is list, must be object")
    if "seconds" in pb and "total_seconds" not in pb:
        errors.append(f'{name}: SCHEMA FAIL — pre_build uses "seconds"')
    if not pb.get("pct_of_total"):
        errors.append(f"{name}: SCHEMA FAIL — pre_build missing pct_of_total")
    if pb.get("orchestrator", "") not in ("argo", "volcano", "docker", "jenkins"):
        errors.append(f"{name}: SCHEMA FAIL — orchestrator={pb.get('orchestrator')}")

    # Timestamp check
    for a in pb.get("actions", []):
        if a.get("start", "?") in ("?", "") or a.get("end", "?") in ("?", ""):
            errors.append(f'{name}: SCHEMA FAIL — action "{a["key"]}" has "?" timestamp')
            break

    # R1: unattributed >= 0
    if unatt < 0:
        errors.append(f"{name}: R1 FAIL — unattributed={unatt:.1f} < 0")

    # R5: zero-duration actions without evidence (cached docker pull etc. is OK)
    empty = [
        a["key"] for a in pb.get("actions", [])
        if a.get("duration_seconds", 0) == 0
        and not a.get("evidence", "").strip()
    ]
    if empty:
        errors.append(f"{name}: R5 FAIL — {len(empty)} zero-duration actions without evidence: {empty}")

    # R7: total_seconds >= action span
    if pb.get("actions"):
        actions_span = sum(a.get("duration_seconds", 0) for a in pb["actions"])
        if pre < actions_span - 1.0:
            errors.append(
                f"{name}: R7 FAIL — total_seconds={pre:.1f}s < sum of durations={actions_span:.1f}s"
            )

    # R8: env_setup catch-all (skip for jenkins — no pod actions)
    if pb.get("orchestrator", "") == "jenkins":
        env_action = None
    else:
        env_action = next((a for a in pb.get("actions", []) if a["key"] == "env_setup"), None)
    if env_action and env_action.get("duration_seconds", 0) > 20:
        pod_actions = [a["key"] for a in pb.get("actions", [])]
        missing_pod = [
            k
            for k in ["pod_git_clone", "submodule_init", "pip_install", "artifact_download", "acl_headers"]
            if k not in pod_actions
        ]
        if len(missing_pod) >= 2:
            errors.append(
                f'{name}: R8 FAIL — env_setup={env_action["duration_seconds"]:.0f}s catch-all, missing {missing_pod}'
            )

    # R9: unattributed target — 5% of total or 10s, whichever is larger
    r9_limit = max(10.0, total * 0.05)
    if unatt > r9_limit:
        errors.append(
            f"{name}: R9 FAIL — unattributed={unatt:.1f}s ({unatt / total * 100:.1f}%) exceeds target ({r9_limit:.0f}s/5%)"
        )

    # pod_scheduling check (non-Docker)
    if pb.get("orchestrator", "") not in ("docker", "jenkins"):
        pod_sched = next((a for a in pb.get("actions", []) if a["key"] == "pod_scheduling"), None)
        if pod_sched and pod_sched.get("duration_seconds", 0) < 1:
            errors.append(
                f"{name}: pod_scheduling={pod_sched['duration_seconds']:.1f}s < 1s — measured WRONG"
            )

    return errors


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} <json-file>")
        sys.exit(1)

    fname = sys.argv[1]
    d = json.load(open(fname))
    builds = d["builds"]

    all_errors = []
    for i, b in enumerate(builds):
        errs = validate_build(b, i)
        all_errors.extend(errs)

    # Meta check
    if not d["meta"].get("analyzed_at"):
        all_errors.append("META: analyzed_at NOT SET")

    ok = sum(
        1
        for b in builds
        if not b.get("_error")
        and b.get("pre_build", {}).get(
            "total_seconds", b.get("pre_build", {}).get("seconds", 0)
        )
        > 0
    )
    empty_count = sum(
        1
        for b in builds
        if not b.get("_error")
        and b.get("pre_build", {}).get(
            "total_seconds", b.get("pre_build", {}).get("seconds", 0)
        )
        == 0
    )
    error_count = len([b for b in builds if b.get("_error")])

    print(f"{ok} analyzed, {empty_count} empty, {error_count} errors")

    if all_errors:
        print("ISSUES:")
        for e in all_errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    main()
