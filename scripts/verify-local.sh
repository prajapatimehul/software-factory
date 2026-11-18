#!/usr/bin/env bash
# verify-local.sh <repo-path>: run a client repo's own checks on this machine and write a record for the commit.
#
# What runs:
#   1. If the repo has a .factory-verify file: each non-empty, non-# line is one command, run from the repo root.
#   2. Otherwise, by detection:
#        package.json    npm test, plus `npm run typecheck`, `npm run lint` and `npm run build` when those scripts exist
#        pyproject.toml, setup.py or a tests/ directory with test_*.py    python3 -m pytest -q
#        Makefile with a test target    make test
# The record goes to <state dir>/verify-local/<HEAD sha>.json and each command's full output to
# <state dir>/verify-local/logs/ (state dir: scripts/_conf.py state_dir, outside every repo).
# A red test is never skipped, retried or given a sleep here: the record says failed.
# Exit 0 = every command passed on a clean tree, 1 = something failed or nothing could run, 2 = usage error.
set -u
repo_arg="${1:-}"
if [ -z "$repo_arg" ] || [ ! -d "$repo_arg" ]; then echo "usage: scripts/verify-local.sh <repo-path>" >&2; exit 2; fi
here="$(cd "$(dirname "$0")" && pwd -P)"
top="$(git -C "$repo_arg" rev-parse --show-toplevel 2>/dev/null)" || { echo "not a git checkout: $repo_arg" >&2; exit 2; }
sha="$(git -C "$top" rev-parse HEAD)"
branch="$(git -C "$top" rev-parse --abbrev-ref HEAD)"
dirty="$(git -C "$top" status --porcelain | wc -l | tr -d ' ')"
state="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import _conf; print(_conf.state_dir())' "$here")" || exit 2
out="$state/verify-local"; logs="$out/logs"; mkdir -p "$logs"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
name="$(basename "$top")"
rows="$logs/${stamp}-${name}-${sha:0:10}.rows"; : > "$rows"
failed=0; ran=0
echo "verify-local: $name $top @ ${sha:0:10} ($branch, $dirty uncommitted paths)"

# run <label> <command string>
run() {
  local label="$1" cmd="$2"
  local log="$logs/${stamp}-${name}-${sha:0:10}-${label}.log"
  local t0; t0=$(date +%s)
  echo "--- $label: $cmd"
  (cd "$top" && bash -c "$cmd") >"$log" 2>&1
  local rc=$?
  local secs=$(( $(date +%s) - t0 ))
  echo "    exit $rc in ${secs}s, log $log"
  if [ $rc -ne 0 ]; then failed=1; tail -n 15 "$log" | sed 's/^/    | /'; fi
  ran=$((ran+1))
  printf '%s\t%s\t%s\t%s\t%s\n' "$label" "$rc" "$secs" "$log" "$cmd" >> "$rows"
}
has_script() { python3 -c 'import json,sys; sys.exit(0 if sys.argv[2] in (json.load(open(sys.argv[1])).get("scripts") or {}) else 1)' "$top/package.json" "$1" 2>/dev/null; }

if [ -f "$top/.factory-verify" ]; then
  i=0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    i=$((i+1)); run "cmd$i" "$line"
  done < "$top/.factory-verify"
else
  if [ -f "$top/package.json" ]; then
    [ -d "$top/node_modules" ] || run npm-ci "npm ci"
    has_script test && run test "npm test"
    has_script typecheck && run typecheck "npm run typecheck"
    has_script lint && run lint "npm run lint"
    has_script build && run build "npm run build"
  fi
  if [ -f "$top/pyproject.toml" ] || [ -f "$top/setup.py" ] || ls "$top"/tests/test_*.py >/dev/null 2>&1; then
    run pytest "python3 -m pytest -q"
  fi
  if [ -f "$top/Makefile" ] && grep -qE '^test:' "$top/Makefile" && [ ! -f "$top/package.json" ]; then
    run make-test "make test"
  fi
fi
if [ "$ran" -eq 0 ]; then
  echo "verify-local: nothing to run in $top. Add a .factory-verify file (one command per line) to the repo." >&2
  failed=1
fi

record="$out/$sha.json"
python3 - "$rows" "$record" "$name" "$top" "$sha" "$branch" "$dirty" "$started" "$failed" <<'PY'
import json, sys
rows, record, name, top, sha, branch, dirty, started, failed = sys.argv[1:]
cmds = []
for ln in open(rows):
    label, rc, secs, log, cmd = ln.rstrip("\n").split("\t", 4)
    cmds.append({"name": label, "cmd": cmd, "exit": int(rc), "seconds": int(secs), "log": log})
# A pass on a dirty tree proves nothing about the commit, so it is recorded as not passed.
passed = failed == "0" and bool(cmds) and int(dirty) == 0
json.dump({"repo": name, "toplevel": top, "sha": sha, "branch": branch, "dirty": int(dirty) > 0, "dirty_paths": int(dirty),
           "started": started, "commands": cmds, "passed": passed}, open(record, "w"), indent=1)
why = "" if passed else (" (commands failed)" if failed != "0" else " (uncommitted changes: commit, then run again)")
print(f"verify-local: {'PASSED' if passed else 'NOT PASSED'}{why} — record {record}")
sys.exit(0 if passed else 1)
PY
