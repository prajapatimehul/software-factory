#!/usr/bin/env python3
"""SubagentStop. The subagent's final report is checked against what the subagent itself saw: every number/id
must appear in its own transcript (prompt + tool results) or in this session's evidence log; every claim line
needs its command. In deny mode a failing report is sent back ONCE per agent with the list (`decision: block`
delivers the reason as the subagent's next instruction), then passes; never when stop_hook_active.
Mode: .claude/gates.conf subagent-stop=deny|warn|off. RULES.md P1 / P5."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import STATE, evidence_forms, evidence_set, gate_mode, read_payload, unmatched_tokens, unsupported_claims, warn


def transcript_text(path):
    """Everything the subagent received: its prompt and every tool result."""
    parts = []
    try:
        with open(path, errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") != "user":
                    continue
                c = (d.get("message") or {}).get("content")
                for x in ([{"type": "text", "text": c}] if isinstance(c, str) else c or []):
                    if isinstance(x, dict) and x.get("type") == "text":
                        parts.append(x.get("text", ""))
                    elif isinstance(x, dict) and x.get("type") == "tool_result":
                        cc = x.get("content")
                        parts.append(cc if isinstance(cc, str) else json.dumps(cc, ensure_ascii=False))
    except Exception:
        pass
    return "\n".join(parts)


def main():
    p = read_payload()
    if not p or p.get("stop_hook_active"):
        return
    mode = gate_mode("subagent-stop")
    msg = p.get("last_assistant_message") or ""
    if mode == "off" or not msg.strip():
        return
    agent = p.get("agent_id") or "unknown"
    state_path = os.path.join(STATE, "subagent-stop-state.json")
    try:
        with open(state_path) as f:
            state = json.load(f)
    except Exception:
        state = {}
    if state.get(agent):
        return   # sent back once already; never loop
    known = evidence_set(p.get("session_id")) | evidence_forms(transcript_text(p.get("agent_transcript_path") or ""))
    nums = unmatched_tokens(msg, known)
    claims = unsupported_claims(msg.split("\n"))
    if not nums and not claims:
        return
    parts = []
    if nums:
        parts.append(f"{len(nums)} number(s)/id(s) that appear in no tool output of this task and not in its prompt: "
                     + ", ".join(o for o, _ in nums[:15]))
    if claims:
        parts.append(f"{len(claims)} claim line(s) without a command: " + " | ".join(repr(c) for c in claims[:5]))
    reason = ("subagent-stop: your report has " + "; and ".join(parts) + ". For each: re-run the command and paste its "
              "output beside the number or claim (`cmd: … → …`), or reword it as 'not checked'. Do not invent a value. Then finish.")
    if mode == "deny":
        os.makedirs(STATE, exist_ok=True)
        state[agent] = 1
        with open(state_path, "w") as f:
            json.dump(state, f)
        print(json.dumps({"decision": "block", "reason": reason}))
        return
    warn("subagent-stop", p.get("session_id"), reason)


try:
    main()
except SystemExit:
    raise
except Exception:
    pass
sys.exit(0)
