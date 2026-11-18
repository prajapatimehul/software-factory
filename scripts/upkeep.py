#!/usr/bin/env python3
"""Upkeep report: what in this repo has gone stale. Read-only, run on demand, fixes nothing.

  upkeep.py [--days 14]

Looks at: drafts never sent, open asks past their chase date, promises past due, claims not re-verified, open tasks
not touched for --days, task files over 150 lines, the state check and the mistake store. Exit 0 always: it is a
report, not a gate."""
import datetime
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import path, read_tsv  # noqa: E402

TODAY = datetime.datetime.now(datetime.timezone.utc).date()
OPEN = ("open", "researching", "waiting-on-client", "blocked")
found = 0


def flag(line):
    global found
    found += 1
    print("  ! " + line)


def age(s):
    m = re.search(r"\d{4}-\d{2}-\d{2}", s or "")
    try:
        return (TODAY - datetime.date.fromisoformat(m.group(0))).days if m else None
    except ValueError:
        return None


def rows(rel):
    try:
        return read_tsv(rel)
    except OSError:
        flag(f"{rel} is missing")
        return []


def main():
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 14
    print(f"upkeep {TODAY} (stale = older than {days} days)")

    print("ledger:")
    for r in rows("ledger/mail.tsv"):
        a = age(r["date_utc"])
        if r["msgid"].startswith("draft:") and a is not None and a > 2:
            flag(f"draft {r['msgid'][6:]} ({r['task']}) is {a} d old and not sent: send it or withdraw it (draft.py --delete)")
    for r in rows("ledger/asks.tsv"):
        if r["status"] != "open":
            continue
        chase = age(r.get("chase_after"))
        a = age(r["date_utc"])
        if chase is not None and chase > 0:
            flag(f"ask {r['ask_id']} is {chase} d past its chase date: {r['wording'][:70]}")
        elif r.get("first_msgid") == "(draft)" and a is not None and a > 2:
            flag(f"ask {r['ask_id']} was drafted {a} d ago and never sent: withdraw it or send the draft")
    for r in rows("ledger/promises.tsv"):
        due = age(r.get("due"))
        if r["status"] in ("open", "overdue") and due is not None and due > 0:
            flag(f"promise {r['promise_id']} is {due} d past due: {r['wording'][:70]}")
    for r in rows("ledger/claims.tsv"):
        a = age(r.get("last_verified") or r.get("date_utc"))
        if (r.get("still_true") or "").lower() not in ("no", "withdrawn") and a is not None and a > days:
            flag(f"claim {r['claim_id']} was last verified {a} d ago; run its verify_cmd: {r['claim_to_client'][:60]}")

    print("tasks:")
    tdir = path("tasks")
    for f in sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []:
        if not re.match(r"T-\d+-.*\.md$", f):
            continue
        text = open(os.path.join(tdir, f), encoding="utf-8", errors="replace").read()
        m = re.search(r"^status:\s*(\S+)", text, re.M)
        n = text.count("\n")
        if n > 150:
            flag(f"{f} is {n} lines: move history to the bottom or to tasks/archive/")
        if m and m.group(1) in OPEN:
            a = int((datetime.datetime.now().timestamp() - os.path.getmtime(os.path.join(tdir, f))) // 86400)
            if a > days:
                flag(f"{f} is {m.group(1)} and was not touched for {a} d: close it, or write why it waits")

    print("checks:")
    here = os.path.dirname(os.path.abspath(__file__))
    for cmd in (["bash", os.path.join(here, "check-state.sh")], [sys.executable, os.path.join(here, "mistakes.py"), "check"]):
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode:
            flag(f"{os.path.basename(cmd[1])} exits {p.returncode}:")
            print("\n".join("      " + l for l in (p.stdout + p.stderr).strip().splitlines()[-8:]))
        for l in p.stdout.splitlines():
            if l.startswith("OWED"):
                flag(l)
    print(f"upkeep: {found} finding(s). Nothing was changed; the owner picks what to fix.")


if __name__ == "__main__":
    main()
