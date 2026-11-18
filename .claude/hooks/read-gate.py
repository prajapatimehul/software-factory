#!/usr/bin/env python3
"""PreToolUse on Read. The history files grow without limit and are never read whole: learning/MISTAKE.md,
learning/LEARNING.md, STATE-LOG.md and mail/raw/*. Once one of them is longer than 400 lines, a Read needs a
limit of 400 or less. A whole read spends the context on history and leaves less for the task.
Mode: .claude/gates.conf read-gate=deny|warn|off."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import file_text, gate, read_payload, rel_path

BIG = re.compile(r"^(learning/MISTAKE\.md|learning/LEARNING\.md|STATE-LOG\.md|mail/raw/.*)$")
MAX = 400


def main():
    p = read_payload()
    if not p or p.get("tool_name") != "Read":
        return
    ti = p.get("tool_input") or {}
    rel = rel_path(ti.get("file_path", ""))
    if not rel or not BIG.match(rel):
        return
    limit = ti.get("limit")
    if isinstance(limit, int) and 0 < limit <= MAX:
        return
    if file_text(ti.get("file_path", "")).count("\n") <= MAX:
        return
    how = ("read one entry with `python3 scripts/mistakes.py show N`, or " if rel.endswith("MISTAKE.md") else "")
    gate("read-gate", p, f"read-gate: {rel} is history and is not read whole. Instead {how}`grep -n` what you need, "
         f"then Read with offset and limit ≤ {MAX}.", default="deny")


try:
    main()
except SystemExit:
    raise
except Exception:
    pass
sys.exit(0)
