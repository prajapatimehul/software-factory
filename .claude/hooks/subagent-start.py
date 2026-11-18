#!/usr/bin/env python3
"""SubagentStart. A subagent starts with CLAUDE.md and its prompt only: no RULES.md, no STATE.md, no session
history. This puts the rules card, the first section of STATE.md and the report contract in front of it.
Context only, capped under the 10,000-character hook limit. Never fails."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import ROOT, context, file_text, read_payload

CONTRACT = ("Report contract in this repo: each claim line carries `cmd:` with the command and its pasted output; every "
            "number or id in the report comes from a tool output of this task or from the task prompt (a SubagentStop "
            "check sends the report back otherwise); an empty or 0 result is not 'absent' until a must-match control (the "
            "same command on a value known to exist) printed something; one file, one row or one case is reported as "
            "that, never as all; 'not checked' is a valid answer and is preferred to a guess. Raw sources over summaries: "
            "read the document, not a paraphrase of it.")


def first_section(text, cap=1800):
    lines = text.split("\n")
    starts = [i for i, l in enumerate(lines) if l.startswith("## ")]
    if not starts:
        return "\n".join(lines[:12])[:cap]
    sec = lines[starts[0]: starts[1] if len(starts) > 1 else len(lines)]
    out = "\n".join(sec)
    if len(out) <= cap:
        return out
    keep = [sec[0]] + [l for l in sec[1:] if "**Next" in l or "**Open" in l][:3]   # Next and Open survive the cut
    return "\n".join(keep + [l for l in sec[1:] if l not in keep and l.strip()])[:cap]


try:
    if read_payload():
        card = file_text(os.path.join(ROOT, "RULES.md"))[:5500]
        state = first_section(file_text(os.path.join(ROOT, "STATE.md"))) or "(STATE.md not readable)"
        ctx = f"{card}\n\n## Current state (the first section of STATE.md)\n{state}\n\n## {CONTRACT}"
        context("SubagentStart", ctx[:9800])
except Exception:
    pass
sys.exit(0)
