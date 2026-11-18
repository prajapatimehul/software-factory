#!/usr/bin/env python3
"""PostToolUse on every tool + UserPromptSubmit. Appends what the tool printed (and what the owner typed) to this
session's evidence log, and its number/id tokens to a token file, so number-gate.py, subagent-stop.py and
stop-check.py can tell a copied number from a typed one without reading the transcript. Never blocks."""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
try:
    from _lib import evidence_forms, read_payload, response_text, session_files
    p = read_payload()
    if not p:
        sys.exit(0)
    log, tokf = session_files(p.get("session_id"))
    if p.get("hook_event_name") == "UserPromptSubmit":
        head, body = "prompt", p.get("prompt", "") or ""
    else:
        ti = p.get("tool_input") or {}
        target = ti.get("command") or ti.get("file_path") or ti.get("pattern") or ti.get("url") or ti.get("prompt") or ""
        head = " ".join(s for s in (p.get("tool_name", "?"), p.get("tool_use_id", ""),
                                    f"agent={p['agent_id']}" if p.get("agent_id") else "", str(target).replace("\n", " ")) if s)
        body = response_text(p)
    body = body[:300_000]
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(log, "a") as f:
        f.write(f"\n=== evidence-record {ts} {head}\n{body}\n")
    forms = evidence_forms(head + "\n" + body)
    if forms:
        with open(tokf, "a") as f:
            f.write("\n".join(sorted(forms)) + "\n")
except Exception:
    pass
sys.exit(0)
