#!/usr/bin/env bash
# /brief: grep every local source for a topic before a question to the client is even considered.
# Prints [ok N] (N files with a hit) or [UNAVAILABLE] per source. The mail archive (mail/raw/) is optional: a fork
# that keeps none gets [not kept], which does not make the search incomplete.
# Usage: scripts/brief.sh "<topic>" ["alt|words|separated|by|pipes"]
here="$(cd "$(dirname "$0")" && pwd -P)"
root="$(python3 "$here/_common.py" root)" || exit 1
repos="$(python3 "$here/_common.py" get CLIENT_REPOS)"
cd "$root" || exit 1
t="${1:-}"; alt="${2:-}"; pat="$t"; [ -n "$alt" ] && pat="$t|$alt"
[ -z "$t" ] && { echo "usage: brief.sh topic [alt|words]"; exit 1; }
EX="--exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=build --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=cdk.out"
src() {
  local name="$1" lim="$2"; shift 2
  local have=()
  for p in "$@"; do [ -e "$p" ] && have+=("$p"); done
  if [ ${#have[@]} -eq 0 ]; then echo "[UNAVAILABLE] $name ($*)"; return; fi
  # shellcheck disable=SC2086
  n=$(grep -rIliE $EX -e "$pat" "${have[@]}" | wc -l | tr -d ' ')
  echo "[ok $n] $name"
  # shellcheck disable=SC2086
  grep -rIniE $EX -e "$pat" "${have[@]}" | head -"$lim" | cut -c1-160 | sed 's/^/    /'
}
echo "BRIEF: $pat"
src "STATE + tasks" 6 STATE.md tasks
src "ledgers (mail / asks / promises / claims)" 6 ledger
src "decisions" 6 decisions
src "LEARNING (what the client told us)" 6 learning/LEARNING.md
src "MISTAKE" 4 learning/MISTAKE.md
src "style" 3 style
if [ -d mail ]; then src "mail archive" 4 mail
else echo "[not kept] mail archive (no mail/ directory; ledger/mail.tsv above is the record of every message)"; fi
for r in $repos; do
  src "$(basename "$r") docs" 4 "$r/docs" "$r/README.md" "$r/CLAUDE.md"
  src "$(basename "$r") code" 4 "$r"
done
echo "Vendor or platform behaviour: read the vendor's own doc page; do not guess."
echo "State of a live system: run the read-only call that answers it, with the environment named explicitly."
echo "END with exactly one: Answered | Deferred | Conflicting | Awaiting a specific answer | Search incomplete"
echo "A question to the client is allowed ONLY under 'Awaiting a specific answer'. 'Search incomplete' is never a question."
