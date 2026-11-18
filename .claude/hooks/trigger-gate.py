#!/usr/bin/env python3
"""A past mistake, shown at the moment it is about to repeat. learning/triggers.tsv has one row per trigger:
id, applies (bash|write|any), regex, action (deny-once|note), entries, rule.
- deny-once (PreToolUse on Bash|Write|Edit): a matching call is refused once with the rule; re-issued unchanged
  in the same session it passes. The refusal is the reminder, not a wall.
- note (PostToolUse on Bash): the rule is added as context after the call.
Counts per trigger (fired / overridden) go to <state dir>/trigger-counts.json: a trigger overridden every time
is noise to remove; one that changed a call is a rule that works. A bad regex row is skipped."""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import STATE, context, deny, new_text, read_payload, read_tsv


def load_json(name):
    try:
        with open(os.path.join(STATE, name)) as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(name, data):
    os.makedirs(STATE, exist_ok=True)
    with open(os.path.join(STATE, name), "w") as f:
        json.dump(data, f, indent=1)


def bump(tid, field):
    counts = load_json("trigger-counts.json")
    counts.setdefault(tid, {"fired": 0, "overridden": 0})[field] += 1
    save_json("trigger-counts.json", counts)


def main():
    p = read_payload()
    if not p:
        return
    tool, ti = p.get("tool_name"), p.get("tool_input") or {}
    if tool == "Bash":
        text, kind = ti.get("command", "") or "", "bash"
    elif tool in ("Write", "Edit"):
        text, kind = new_text(tool, ti), "write"
    else:
        return
    rows = []
    for r in read_tsv("learning/triggers.tsv"):
        try:
            if (r.get("applies") or "any") in (kind, "any") and r.get("regex") and re.search(r["regex"], text):
                rows.append(r)
        except re.error:
            continue
    label = lambda r: f"{r.get('id')}" + (f" (mistake {r['entries']})" if r.get("entries") else "")
    if p.get("hook_event_name") == "PreToolUse":
        for r in rows:
            if r.get("action") != "deny-once":
                continue
            key = hashlib.sha1(f"{p.get('session_id')}|{r.get('id')}|{text}".encode()).hexdigest()[:16]
            seen = load_json("trigger-state.json")
            if key in seen:
                bump(r.get("id"), "overridden")
                continue
            seen[key] = r.get("id")
            save_json("trigger-state.json", seen)
            bump(r.get("id"), "fired")
            deny(f"trigger {label(r)}: {r.get('rule')} If this call is right anyway, re-issue it unchanged and it will pass.")
    elif p.get("hook_event_name") == "PostToolUse":
        notes = [r for r in rows if r.get("action") == "note"]
        for r in notes:
            bump(r.get("id"), "fired")
        if notes:
            context("PostToolUse", " ".join(f"note {label(r)}: {r.get('rule')}" for r in notes))


try:
    main()
except SystemExit:
    raise
except Exception:
    pass
sys.exit(0)
