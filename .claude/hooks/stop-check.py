#!/usr/bin/env python3
"""Stop. Three checks, each blocking once so a turn can always end:
 (a) a mail row was written today and neither STATE.md nor a task file was touched after it;
 (b) `scripts/mistakes.py check` is red (the mistake log and its index disagree), when that script exists;
 (c) done-needs-proof: this turn edited a file and the last message claims done / fixed / live / works ...
     with no Bash/Read/Grep run after the last edit (a turn = records since the last prompt in the evidence log).
Never blocks when stop_hook_active; never fails. RULES.md P1 / P3."""
import datetime
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import CLAIM, ROOT, STATE, file_text, read_payload, session_files

RECORD = re.compile(r"^=== evidence-record \S+ (\S+)(.*)$")
CHECKS = ("Bash", "Read", "Grep", "Glob", "WebFetch", "WebSearch", "Agent", "Task")
STATE_FILE = os.path.join(STATE, "stop-state.json")


def mail_rule():
    mail = os.path.join(ROOT, "ledger", "mail.tsv")
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    try:
        if not any(l.startswith(today) for l in open(mail)):
            return None
        tasks = glob.glob(os.path.join(ROOT, "tasks", "*.md"))
        touched = max([os.path.getmtime(os.path.join(ROOT, "STATE.md"))] + [os.path.getmtime(f) for f in tasks])
        if os.path.getmtime(mail) > touched:
            return ("stop-check: a mail row was written today but neither STATE.md nor a task file was updated after it. "
                    "Record it (the task's Sent/Next lines, STATE.md) before stopping.")
    except OSError:
        return None


def mistakes_rule():
    script = os.path.join(ROOT, "scripts", "mistakes.py")
    if not os.path.exists(script):
        return None
    r = subprocess.run([sys.executable, script, "check"], env={**os.environ, "FACTORY_ROOT": ROOT},
                       capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        return None
    lines = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()]
    return "stop-check: `python3 scripts/mistakes.py check` is red: " + " | ".join(lines[:4]) + ". Fix it before stopping."


def last_message(p):
    msg = p.get("last_assistant_message")
    if msg:
        return msg
    for line in reversed(file_text(p.get("transcript_path") or "").splitlines()[-200:]):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "assistant":
            c = (d.get("message") or {}).get("content")
            text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
            if text.strip():
                return text
    return ""


def proof_rule(p):
    m = CLAIM.search(last_message(p))
    if not m:
        return None
    recs = [(r.group(1), r.group(2).strip()) for r in map(RECORD.match, file_text(session_files(p.get("session_id"))[0]).splitlines()) if r]
    prompts = [i for i, (tool, _) in enumerate(recs) if tool == "prompt"]
    turn = recs[prompts[-1] + 1:] if prompts else recs
    edits = [i for i, (tool, _) in enumerate(turn) if tool in ("Write", "Edit", "NotebookEdit")]
    if not edits or any(tool in CHECKS for tool, _ in turn[edits[-1] + 1:]):
        return None
    files = sorted({os.path.basename(turn[i][1].split()[-1]) for i in edits if turn[i][1].split()})
    return (f"stop-check: this turn edited {', '.join(files)[:200]} and the last message says {m.group(0)!r} with no check "
            "run after the last edit. Run the command that could falsify the claim (the test, a read-back, the script) "
            "and paste its output, or reword the claim as 'not checked'. (RULES.md P1)"), len(prompts)


def main():
    p = read_payload()
    if not p or p.get("stop_hook_active"):
        return
    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
    except Exception:
        st = {}
    mine = st.setdefault(p.get("session_id") or "unknown", {})

    def block(key, value, reason):
        mine[key] = value
        os.makedirs(STATE, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(st, f)
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    r = mail_rule()
    if r and not mine.get("mail"):
        block("mail", 1, r)
    r = mistakes_rule()
    if r and not mine.get("mistakes"):
        block("mistakes", 1, r)
    r = proof_rule(p)
    if r and mine.get("proof_turn") != r[1]:
        block("proof_turn", r[1], r[0])


try:
    main()
except SystemExit:
    raise
except Exception:
    pass
sys.exit(0)
