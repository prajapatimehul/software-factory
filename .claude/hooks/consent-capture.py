#!/usr/bin/env python3
"""UserPromptSubmit: when the owner's own prompt carries the production token or a send instruction, record a
consent file that lives CONSENT_TTL_MIN minutes. The gates accept the token in a command only while it is live.
Text the owner did not type (task notifications, pasted blocks, '> ' quotes) is removed first, and a line that
only describes the token ("needs a PROD-WRITE-OK") is not consent. Never blocks."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))


def capture(payload) -> list:
    import _consent
    if payload.get("hook_event_name", "UserPromptSubmit") != "UserPromptSubmit":
        return []
    out = []
    for tok, (excerpt, drafts) in _consent.detect(_consent.human_text(payload.get("prompt", "") or "")).items():
        _consent.write(tok, excerpt, "prompt", payload.get("session_id", ""), drafts)
        rec = _consent.live(tok)
        name = _consent.PROD_TOKEN if tok == "PROD" else tok
        out.append(f"{name} until {rec['expires'] if rec else '?'}" + (f" for {', '.join(drafts)}" if drafts else ""))
    return out


if __name__ == "__main__":
    try:
        got = capture(json.load(sys.stdin))
        if got:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
                  "consent recorded from the owner's prompt: " + "; ".join(got) + " (the gates accept it until then)."}}))
    except Exception:
        pass
    sys.exit(0)
