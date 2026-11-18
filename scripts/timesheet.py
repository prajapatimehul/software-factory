#!/usr/bin/env python3
"""Sum timesheet/TIMESHEET.md by day and month, billed against open. Numbers come from this script, never from memory.

  timesheet.py [--days]

TIMESHEET.md is a table `| YYYY-MM-DD | work | hours |` plus optional settings lines anywhere in the file:
  rate: 50              money per hour (any currency; the script prints the bare number)
  budget: 80            hours per month; a month above it is flagged
  billed: 40  INV-3     hours already invoiced (repeat the line per invoice)
  not-billed: 2.5       hours logged but written off
A row of 3 hours or more with no clock time in its text is flagged: hours come from timestamps (commits, mail
headers, logs), not from a feeling."""
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import path  # noqa: E402

ROW = re.compile(r"\|\s*(\d{4}-\d\d-\d\d)\s*\|(.*)\|\s*([\d.]+)\s*\|\s*$")
SETTING = re.compile(r"^\s*(rate|budget|billed|not-billed):\s*([\d.]+)", re.I)


def main():
    f = path("timesheet", "TIMESHEET.md")
    if not os.path.exists(f):
        print("timesheet: no timesheet/TIMESHEET.md yet. Create it with a '| Date | Work | Hours |' table; see this "
              "script's header for the settings lines.")
        return
    rows, s = [], defaultdict(float)
    for line in open(f):
        m = ROW.match(line)
        if m:
            rows.append((m.group(1), m.group(2).strip(), float(m.group(3))))
            continue
        m = SETTING.match(line)
        if m:
            k = m.group(1).lower()
            s[k] = s[k] + float(m.group(2)) if k in ("billed", "not-billed") else float(m.group(2))
    byday, bymon = defaultdict(float), defaultdict(float)
    for d, _, h in rows:
        byday[d] += h
        bymon[d[:7]] += h
    total = sum(byday.values())
    open_h = total - s["billed"] - s["not-billed"]
    money = f"  (= {open_h * s['rate']:.0f} at {s['rate']:g}/h)" if s["rate"] else ""
    print(f"rows {len(rows)}  logged {total:.2f} h  billed {s['billed']:.2f} h  not billed {s['not-billed']:.2f} h  open {open_h:.2f} h{money}")
    for m in sorted(bymon):
        over = f"  <- over the {s['budget']:g} h/month budget" if s["budget"] and bymon[m] > s["budget"] else ""
        print(f"  {m}: {bymon[m]:.2f} h{over}")
    noanchor = [(d, h, w[:60]) for d, w, h in rows if h >= 3 and not re.search(r"\d\d:\d\d", w)]
    if noanchor:
        print("rows of 3 h or more with no clock time in the text (check before invoicing):")
        for d, h, w in noanchor:
            print(f"  {d} {h:>5} h  {w}")
    if "--days" in sys.argv:
        for d in sorted(byday):
            print(f"  {d} {byday[d]:.2f}")


if __name__ == "__main__":
    main()
