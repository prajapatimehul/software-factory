#!/usr/bin/env python3
"""PreToolUse on Write|Edit into the state files. Every time, id, decimal and integer of two or more digits in
the NEW text must already exist in this session's evidence (what a tool printed or the owner typed) or in the
file itself. A derived value passes on a line that says "computed" when its other tokens matched.
Mode: .claude/gates.conf number-gate=deny|warn|off. RULES.md P2 / P4."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import evidence_forms, evidence_set, file_text, gate, new_text, read_payload, rel_path, tokens

GATED = re.compile(r"^(STATE\.md|STATE-LOG\.md|RULES\.md|tasks/.*\.md|ledger/.*\.tsv|learning/.*\.(md|tsv)|docs/.*\.md|decisions/.*\.md)$")


def main():
    p = read_payload()
    if not p or p.get("tool_name") not in ("Write", "Edit"):
        return
    ti = p.get("tool_input") or {}
    rel = rel_path(ti.get("file_path", ""))
    if not rel or not GATED.match(rel):
        return
    text = new_text(p["tool_name"], ti)
    known = evidence_set(p.get("session_id")) | evidence_forms(file_text(ti.get("file_path")))
    bad = []
    for line in text.split("\n"):
        toks = tokens(line)
        unmatched = [(o, n) for _, o, n in toks
                     if n not in known and not (n.count(":") == 1 and any(k.startswith(n + ":") for k in known))]
        if "computed" in line.lower() and len(unmatched) == 1 and len(toks) >= 2:
            continue   # one derived value beside its matched inputs
        for o, _ in unmatched:
            if o not in [b[0] for b in bad]:
                bad.append((o, line.strip()[:90]))
    if bad:
        gate("number-gate", p, f"number-gate: {len(bad)} token(s) in the new text appear in no tool output or prompt of this "
             "session: " + "; ".join(f"{o} (in: {l!r})" for o, l in bad[:12])
             + ". Paste them from a tool output (run the command if it has not run in this session), write a derived "
               "value with its inputs and the word computed on the same line, or leave the number out. (RULES.md P2/P4)")


try:
    main()
except SystemExit:
    raise
except Exception:
    pass
sys.exit(0)
