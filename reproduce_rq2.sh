#!/usr/bin/env bash
# RQ2 (target selection): Logic Group + first-draft harness from a
# functionality prompt, then the entry-selection match.
#
#   ./reproduce_rq2.sh all                          # the 100 tasks, Claude Sonnet 5
#   MODEL=gemini/gemini-3.5-flash ./reproduce_rq2.sh all   # the same with Gemini 3.5
#   ./reproduce_rq2.sh zlib-c1 libyaml-c1           # some tasks
#
# Prompts: benchmark/rq2_prompts.jsonl (60 name the target, 40 describe the
# feature only).  Nothing is built or fuzzed.  Results in
# work/rq2/<model>/<task>/ and the table in work/rq2/<model>/match.json.
# Needs ANTHROPIC_API_KEY (or GEMINI_API_KEY for a Gemini model).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
export QF_WORK=${QF_WORK:-$PWD/work}
JOBS=${JOBS:-3}
MODEL=${MODEL:-claude-sonnet-5}
[ $# -ge 1 ] || { sed -n '2,12p' "$0"; exit 1; }
case "$1" in
  all) CASES=$(tail -n +2 benchmark/cases.tsv | cut -f1) ;;
  subset25) CASES=$(cat benchmark/subset_25.txt) ;;
  *) CASES="$*" ;;
esac

./reproduce.sh --setup-only $CASES
PY=$PWD/.venv/bin/python
case "$MODEL" in
  *gemini*) [ -n "${GEMINI_API_KEY:-}" ] || { echo "set GEMINI_API_KEY" >&2; exit 1; } ;;
  *) [ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "set ANTHROPIC_API_KEY" >&2; exit 1; } ;;
esac
export AGF_CALLGRAPH_DIR=$QF_WORK/callgraphs MODEL PY
OUT=$QF_WORK/rq2/${MODEL//\//_}
mkdir -p "$OUT"
printf '%s\n' $CASES | xargs -P "$JOBS" -I{} bash -c \
  '$PY scripts/rq2/run_rq2.py {} --model "$MODEL" > "'"$OUT"'/{}.log" 2>&1 && echo "{}: done" || echo "{}: failed (see '"$OUT"'/{}.log)"'
$PY scripts/rq2/match.py "$OUT"
