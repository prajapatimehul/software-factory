---
name: hours
description: Hours, invoice and budget questions. Sums timesheet/TIMESHEET.md by script and reports billed against open; never types a number from memory.
---
# /hours

`python3 scripts/timesheet.py [--days]`. Every number in the answer is copied from its output.

- Rows (`| YYYY-MM-DD | work, with clock times | hours |`) are added only from timestamps: commit times, mail headers,
  log times. The script flags a row of 3 hours or more with no clock time in its text.
- Rate, budget and invoiced hours are settings lines in the same file (`rate:`, `budget:`, `billed:`, `not-billed:`);
  the commercial facts behind them, with their sources, are in `TERMS.md`. Change TERMS.md first.
- An invoice or an hours figure sent to the client is a claim: it goes through `/reply` like any other.
