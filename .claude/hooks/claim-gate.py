#!/usr/bin/env python3
"""PreToolUse on Write|Edit into STATE.md, STATE-LOG.md, tasks/, ledger/claims.tsv, docs/ and decisions/.
A NEW line that makes a claim ("done", "live", "works", "empty", "blocked", "all of them" ...) must carry its
command within three lines: a `cmd:` line, or a backticked command followed by an arrow. Headings, Next/Open/TODO
lines, questions and "not checked" lines are exempt. This is the gate at the place a claim is born.
Mode: .claude/gates.conf claim-gate=deny|warn|off. RULES.md P1."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import gate, new_text, read_payload, rel_path, unsupported_claims

GATED = re.compile(r"^(STATE\.md|STATE-LOG\.md|tasks/.*\.md|ledger/claims\.tsv|docs/.*\.md|decisions/.*\.md)$")


def main():
    p = read_payload()
    if not p or p.get("tool_name") not in ("Write", "Edit"):
        return
    ti = p.get("tool_input") or {}
    rel = rel_path(ti.get("file_path", ""))
    if not rel or not GATED.match(rel):
        return
    bad = unsupported_claims(new_text(p["tool_name"], ti).split("\n"))
    if bad:
        gate("claim-gate", p, f"claim-gate: {len(bad)} new line(s) make a claim without the command that could falsify it: "
             + " | ".join(repr(b) for b in bad[:6])
             + ". Add `cmd: <command>` and its pasted output within three lines (or `command` → output), or reword "
               "the line as 'not checked'. (RULES.md P1)")


try:
    main()
except SystemExit:
    raise
except Exception:
    pass
sys.exit(0)
