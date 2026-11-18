#!/usr/bin/env bash
# /checkpoint and scripts/upkeep.py run this (session start prints only STATE.md size, age and a count of stale
# stamps): STATE.md must hold "now" only, with fresh stamps, and the indexes must agree with the files.
# Prints a short digest. Exit 1 when something has to be fixed before work goes on.
here="$(cd "$(dirname "$0")" && pwd -P)"
root="$(python3 "$here/_common.py" root)" || exit 1
max="$(python3 "$here/_common.py" get STATE_MAX_LINES)"
cd "$root" || exit 1
bad=0

# Stale stamps: a "[verified YYYY-MM-DD" or "[recorded YYYY-MM-DD" older than 7 days is re-verified before it is repeated.
python3 - <<'PY' || bad=1
import datetime, re, sys
today = datetime.datetime.now(datetime.timezone.utc).date()
stale = []
try:
    lines = open("STATE.md", encoding="utf-8", errors="replace").read().splitlines()
except OSError:
    print("check-state: no STATE.md"); sys.exit(1)
for line in lines:
    m = re.search(r"\[(?:verified|recorded) (\d{4}-\d{2}-\d{2})", line)
    if not m:
        continue
    try:
        age = (today - datetime.date.fromisoformat(m.group(1))).days
    except ValueError:
        continue
    if age > 7:
        stale.append((age, line))
for age, line in stale[:5]:
    print(f"STALE ({age} d): {line[:110]}")
if stale:
    print(f"check-state: {len(stale)} STATE.md line(s) older than 7 days — re-verify before relying on them.")
    sys.exit(1)
print("check-state: STATE.md stamps fresh.")
PY

# STATE.md holds NOW only; history lives in STATE-LOG.md.
n=$(wc -l < STATE.md 2>/dev/null | tr -d ' '); n=${n:-0}
if [ "$n" -gt "$max" ]; then
  echo "STATE.md is $n lines (limit $max): move the older dated block(s) to the top of STATE-LOG.md."; bad=1
fi

# Index vs task files.
for f in tasks/T-*.md; do
  [ -e "$f" ] || continue
  id=$(basename "$f" | cut -d- -f1-2); st=$(grep -m1 '^status:' "$f" | awk '{print $2}')
  ist=$(grep -E "^\| $id \|" tasks/TASKS.md 2>/dev/null | cut -d'|' -f3 | tr -d ' ')
  if [ -n "$ist" ] && [ "$st" != "$ist" ]; then echo "MISMATCH $id: file says '$st', TASKS.md says '$ist'"; bad=1; fi
done

# A hedged clock time means nobody read the clock.
fab=$(grep -nE '20[0-9]{2}-[0-9]{2}-[0-9]{2}[^|]*~[0-9]{1,2}:[0-9]{2}' STATE.md tasks/T-*.md 2>/dev/null | head -5)
[ -n "$fab" ] && { echo "TYPED TIME? a dated line with ~HH:MM — read the time back from the tool, or give the id and no time:"; echo "$fab" | sed 's/^/  /'; }

# An id used twice in a ledger: ids come from the scripts, never typed.
for f in ledger/asks.tsv ledger/promises.tsv ledger/claims.tsv; do
  [ -f "$f" ] || continue
  d=$(sed 1d "$f" | cut -f1 | sort | uniq -d | tr '\n' ' ')
  if [ -n "$d" ]; then echo "DUPLICATE ID in $f: $d"; bad=1; fi
done

echo "open tasks: $(grep -cE '^\| T-[0-9]+ \| (open|researching|blocked) ' tasks/TASKS.md 2>/dev/null); waiting-on-client: $(grep -cE '^\| T-[0-9]+ \| waiting-on-client ' tasks/TASKS.md 2>/dev/null)"
echo "open asks (do not re-send): $(awk -F'\t' 'NR>1 && ($8=="open"||$8=="do-not-chase"){printf "%s ", $1}' ledger/asks.tsv 2>/dev/null)"
echo "open promises: $(awk -F'\t' 'NR>1 && ($8=="open"||$8=="overdue"){printf "%s(%s) ", $1, $8}' ledger/promises.tsv 2>/dev/null)"

# The mistake store: RULES.md counts equal learning/mistakes.tsv, every heading has a row.
python3 "$here/mistakes.py" check 2>&1 | tail -4
[ "${PIPESTATUS[0]}" -ne 0 ] && bad=1
exit $bad
