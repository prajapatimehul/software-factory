#!/usr/bin/env bash
# Fetch and report branch, ahead/behind and dirty count for every repo in CLIENT_REPOS and for this repo.
# It never merges, pulls or checks anything out.
here="$(cd "$(dirname "$0")" && pwd -P)"
root="$(python3 "$here/_common.py" root)" || exit 1
repos="$(python3 "$here/_common.py" get CLIENT_REPOS)"
cd "$root" || exit 1
for r in $repos .; do
  name="$(basename "$(cd "$r" 2>/dev/null && pwd -P)")"; name="${name:-$r}"
  if ! git -C "$r" rev-parse --git-dir >/dev/null 2>&1; then echo "$name: not a git checkout ($r)"; continue; fi
  git -C "$r" fetch -q --all 2>/dev/null || echo "$name: fetch failed (offline or no access); numbers below may be old"
  b=$(git -C "$r" branch --show-current); b=${b:-"(detached)"}
  up=$(git -C "$r" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)
  if [ -n "$up" ]; then ab=$(git -C "$r" rev-list --left-right --count "$up...HEAD" | awk '{print "behind "$1" ahead "$2}'); else ab="no upstream"; fi
  dirty=$(git -C "$r" status --short | wc -l | tr -d ' ')
  echo "$name: $b  $ab  dirty:$dirty"
done
