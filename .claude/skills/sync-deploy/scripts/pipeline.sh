#!/bin/bash
# CI/CD Build Analysis Pipeline — mechanical steps
# Usage: bash pipeline.sh [--force-fetch] [--quick] [--skip-push]
#
# Reads repos.txt, fetches new data (only for changed PRs),
# AI analysis handled by Claude, then normalize → generate → push.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
REPOS_FILE="$PROJECT_DIR/repos.txt"
JSON_ORG="$PROJECT_DIR/json-org"
DOWNLOAD_SCRIPT="$PROJECT_DIR/scripts/download.py"
NORMALIZE_SCRIPT="$SCRIPT_DIR/../../build-log-normalizer/scripts/normalize.py"

FORCE_FETCH=false
SKIP_PUSH=false
QUICK_MODE=false

for arg in "$@"; do
  case $arg in
    --force-fetch) FORCE_FETCH=true ;;
    --skip-push)   SKIP_PUSH=true ;;
    --quick)       QUICK_MODE=true ;;
  esac
done

cd "$PROJECT_DIR"

# ── Step 0: Validate ──
if [ ! -f "$REPOS_FILE" ]; then
  echo "ERROR: repos.txt not found at $REPOS_FILE"
  echo "Create it with one GitCode repo URL per line, e.g.:"
  echo "  https://gitcode.com/Ascend/pytorch"
  echo "  https://gitcode.com/Ascend/MindIE-LLM"
  exit 1
fi

mkdir -p "$JSON_ORG"

echo "=== Pipeline Start: $(date) ==="
echo "Repos file: $REPOS_FILE"
echo "Mode: force_fetch=$FORCE_FETCH quick=$QUICK_MODE skip_push=$SKIP_PUSH"
echo ""

# ── Quick mode: skip fetch & AI analysis ──
if [ "$QUICK_MODE" = true ]; then
  echo "=== Quick mode: normalize + generate + push only ==="
  python3 "$NORMALIZE_SCRIPT"
  python3 generate.py
  if [ "$SKIP_PUSH" = false ]; then
    git add -A
    git commit -m "sync: quick refresh ($(date +%Y-%m-%d))" || echo "  Nothing to commit"
    git push
    echo ""
    echo "=== Pipeline Complete ==="
    echo "Page: https://kerer-ai.github.io/log-report/"
  fi
  exit 0
fi

# ── Step 1: Check PR changes & fetch ──
FETCH_COUNT=0
SKIP_COUNT=0
FAIL_COUNT=0
declare -A CHANGED_REPOS  # repos that need AI re-analysis

echo "=== Phase 1: Checking PR changes ==="
echo ""

CI_BACKEND="openlibing"  # default backend

while IFS= read -r line; do
  # Detect CI_BACKEND directive before skipping comments
  if [[ "$line" =~ ^#[[:space:]]*CI_BACKEND:(.*) ]]; then
    CI_BACKEND="${BASH_REMATCH[1]}"
    echo "  [CI] Backend set to: $CI_BACKEND"
    continue
  fi
  # Skip comments and empty lines
  [[ "$line" =~ ^#.*$ ]] && continue
  [[ -z "$line" ]] && continue

  REPO_URL="$line"
  REPO_PATH=$(echo "$REPO_URL" | sed 's|https://gitcode.com/||')
  REPO_NAME=$(echo "$REPO_PATH" | cut -d'/' -f2)
  OUTPUT_FILE="$JSON_ORG/${REPO_NAME}_build_analysis.json"
  WORK_FILE="$PROJECT_DIR/${REPO_NAME}_build_analysis.json"

  # ── Check if PR changed (unless --force-fetch) ──
  NEED_FETCH=true
  if [ "$FORCE_FETCH" = false ] && [ -f "$OUTPUT_FILE" ]; then
    EXISTING_PR=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['meta']['pr'])" 2>/dev/null || echo "0")
    # Lightweight PR check without full fetch
    LATEST_PR=$(gc pr list -R "$REPO_PATH" --state merged -L 1 2>/dev/null | grep -oP '#\d+' | tr -d '#' || echo "0")
    if [ "$EXISTING_PR" = "$LATEST_PR" ] && [ "$LATEST_PR" != "0" ]; then
      echo "  SKIP $REPO_NAME: PR #$LATEST_PR unchanged"
      SKIP_COUNT=$((SKIP_COUNT + 1))
      # Ensure working dir has analyzed copy
      if [ -f "$OUTPUT_FILE" ] && [ ! -f "$WORK_FILE" ]; then
        cp "$OUTPUT_FILE" "$WORK_FILE"
      fi
      NEED_FETCH=false
    else
      echo "  CHANGED $REPO_NAME: PR #$EXISTING_PR → #$LATEST_PR"
    fi
  elif [ "$FORCE_FETCH" = true ]; then
    echo "  FORCE $REPO_NAME: re-fetching (--force-fetch)"
  else
    echo "  NEW $REPO_NAME: first fetch"
  fi

  if [ "$NEED_FETCH" = false ]; then
    continue
  fi

  # Mark for Stage 1-3 (AI URL discovery → download → AI analysis)
  echo "  QUEUED $REPO_PATH — Stage 1-3 needed"
  CHANGED_REPOS["$REPO_NAME"]="$REPO_PATH"
  FETCH_COUNT=$((FETCH_COUNT + 1))
  continue

  # Reset CI_BACKEND to default for next repo
  CI_BACKEND="openlibing"
  echo ""
done < "$REPOS_FILE"

echo "=== Phase 1 Complete ==="
echo "Fetched: $FETCH_COUNT | Skipped: $SKIP_COUNT | Failed: $FAIL_COUNT"
echo "Needs analysis: ${#CHANGED_REPOS[@]} repos"
for r in "${!CHANGED_REPOS[@]}"; do
  echo "  - $r (${CHANGED_REPOS[$r]})"
done
echo ""

# ── Step 2 & 3: AI analysis (Claude handles via sync-deploy skill) ──
# Export changed repos for the skill to reference
printf '%s\n' "${!CHANGED_REPOS[@]}" > /tmp/sync_changed_repos.txt
echo "Changed repos written to /tmp/sync_changed_repos.txt"
echo "=== Next: AI analysis (Claude) ==="

# ── Steps 4-6: Normalize + Generate + Push ──
finalize() {
  echo ""
  echo "=== Phase 4: Normalize + Generate + Push ==="
  python3 "$NORMALIZE_SCRIPT"
  echo ""
  python3 generate.py
  echo ""
  if [ "$SKIP_PUSH" = false ]; then
    echo "=== Push to GitHub ==="
    git add -A
    git commit -m "sync: update build analysis ($(date +%Y-%m-%d))" || echo "  Nothing to commit"
    git push
    echo ""
    echo "=== Pipeline Complete ==="
    echo "Page: https://kerer-ai.github.io/log-report/"
  else
    echo "SKIP push (--skip-push)"
  fi
}

# Export for use after AI analysis
export -f finalize
export NORMALIZE_SCRIPT
export SKIP_PUSH

echo ""
echo "After AI analysis completes, run:"
echo "  bash $SCRIPT_DIR/pipeline.sh --quick"
echo ""
