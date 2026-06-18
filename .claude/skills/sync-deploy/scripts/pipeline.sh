#!/bin/bash
# CI/CD Build Analysis Pipeline — mechanical steps
# Usage: bash pipeline.sh [--force-fetch] [--skip-push]
#
# Reads repos.txt, fetches new data, normalizes, generates, pushes.
# AI analysis is handled by Claude via the sync-deploy skill.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
REPOS_FILE="$PROJECT_DIR/repos.txt"
JSON_ORG="$PROJECT_DIR/json-org"
FORCE_FETCH=false
SKIP_PUSH=false

for arg in "$@"; do
  case $arg in
    --force-fetch) FORCE_FETCH=true ;;
    --skip-push) SKIP_PUSH=true ;;
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
echo "Force fetch: $FORCE_FETCH"
echo ""

# ── Step 1: Fetch changed repos ──
FETCH_COUNT=0
SKIP_COUNT=0
while IFS= read -r line; do
  # Skip comments and empty lines
  [[ "$line" =~ ^#.*$ ]] && continue
  [[ -z "$line" ]] && continue

  REPO_URL="$line"
  REPO_PATH=$(echo "$REPO_URL" | sed 's|https://gitcode.com/||')
  REPO_NAME=$(echo "$REPO_PATH" | cut -d'/' -f2)
  OUTPUT_FILE="$JSON_ORG/${REPO_NAME}_build_analysis.json"

  if [ "$FORCE_FETCH" = false ] && [ -f "$OUTPUT_FILE" ]; then
    EXISTING_PR=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['meta']['pr'])" 2>/dev/null || echo "0")
    LATEST_PR=$(gc pr list -R "$REPO_PATH" --state merged -L 1 2>&1 | grep -oP '#\d+' | tr -d '#' || echo "0")
    if [ "$EXISTING_PR" = "$LATEST_PR" ] && [ "$LATEST_PR" != "0" ]; then
      echo "SKIP $REPO_NAME: PR #$LATEST_PR unchanged"
      SKIP_COUNT=$((SKIP_COUNT + 1))
      continue
    fi
    echo "UPDATE $REPO_NAME: PR #$EXISTING_PR → #$LATEST_PR"
  fi

  echo "FETCH $REPO_NAME from $REPO_PATH"
  RESULT=$(python3 .claude/skills/gitcode-build-time-analyzer/scripts/fetch_build_logs.py \
    --repo "$REPO_PATH" --latest-merged -o "$OUTPUT_FILE" 2>&1) || true

  if echo "$RESULT" | grep -q "Template written"; then
    echo "  OK: $(echo "$RESULT" | grep 'Template written')"
    FETCH_COUNT=$((FETCH_COUNT + 1))
  elif echo "$RESULT" | grep -q "No passed build"; then
    echo "  WARN: No passed builds, running PR fallback..."
    # PR fallback scan
    FOUND=false
    for pr_num in $(gc pr list -R "$REPO_PATH" --state merged -L 20 2>&1 | grep -oP '#\d+' | tr -d '#'); do
      fb_result=$(python3 .claude/skills/gitcode-build-time-analyzer/scripts/fetch_build_logs.py \
        --repo "$REPO_PATH" --pr "$pr_num" -o "/tmp/test_${REPO_NAME}.json" 2>&1) || true
      if echo "$fb_result" | grep -q "Template written"; then
        cp "/tmp/test_${REPO_NAME}.json" "$OUTPUT_FILE"
        echo "  FOUND: PR #$pr_num"
        FETCH_COUNT=$((FETCH_COUNT + 1))
        FOUND=true
        break
      fi
      rm -f "/tmp/test_${REPO_NAME}.json"
    done
    if [ "$FOUND" = false ]; then
      echo "  ERROR: No passed builds in last 20 PRs"
    fi
  else
    echo "  ERROR: $RESULT"
  fi
  echo ""
done < "$REPOS_FILE"

echo "Fetch complete: $FETCH_COUNT fetched, $SKIP_COUNT skipped"
echo ""

# ── Step 2 & 3 are handled by Claude (AI analysis) ──
echo "=== Next: AI analysis (Claude) ==="
echo "Files ready for analysis in $JSON_ORG/"
echo ""

# ── Steps 4-5: Normalize + Generate (run after AI analysis) ──
normalize_and_generate() {
  echo "=== Normalize ==="
  python3 .claude/skills/build-log-normalizer/scripts/normalize.py
  echo ""
  echo "=== Generate ==="
  python3 generate.py
  echo ""
}

# ── Step 6: Push ──
push_to_github() {
  if [ "$SKIP_PUSH" = true ]; then
    echo "SKIP push (--skip-push)"
    return
  fi
  echo "=== Push to GitHub ==="
  git add -A
  git commit -m "sync: update build analysis data ($(date +%Y-%m-%d))" || echo "  Nothing to commit"
  git push
  echo ""
  echo "=== Pipeline Complete ==="
  echo "Page: https://kerer-ai.github.io/log-report/"
}

# Export functions for use by Claude
export -f normalize_and_generate push_to_github

echo "After AI analysis is complete, run:"
echo "  bash scripts/pipeline.sh --finish"
echo ""
