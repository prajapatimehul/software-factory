#!/usr/bin/env python3
"""PreToolUse (Bash|Write|Edit|NotebookEdit): keeps consent human-made.

Refuses:
  - a Write/Edit into the consent directory or into a session transcript (~/.claude/projects/**.jsonl);
  - a Bash command that sets FACTORY_STATE_DIR or FACTORY_ROOT (the tests' overrides: a command could point
    send.py at a fake consent directory);
  - a Bash command that names the consent directory, unless it only reads or removes (ls, cat, stat, rm) or runs
    `_consent.py check|status`;
  - a Bash command that writes into a transcript .jsonl (a forged prompt would mint consent);
  - a run of scripts/send.py without a live SEND consent for that draft id (send.py checks again itself).
Fails closed on an unparseable payload."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

READ_ONLY = ("ls", "cat", "stat", "rm", "head", "file")
SEND_RUN = re.compile(r"(?:^|[;&|(`\n\"'])\s*(?:(?:\w+=\S*|nohup|env|exec|command|time|sudo)\s+)*"
                      r"(?:python3?(?:\.\d+)?\s+(?:-\w+\s+)*)?[\"']?(?:\S*/)?scripts/send\.py\b([^;&|\n]*)")
TRANSCRIPT_WRITE = re.compile(r">>?\s*\S*\.jsonl|\btee\b[^|;&]*\.jsonl|\bsed\s+(?:-\w*\s+)*-i[^|;&]*\.jsonl"
                              r"|\b(?:cp|mv|dd)\b[^|;&]*\.jsonl\s*(?:$|[;&|])|\btruncate\b[^|;&]*\.jsonl")


def block(msg):
    print(f"consent-guard: BLOCKED - {msg}", file=sys.stderr)
    return 2


def main() -> int:
    try:
        p = json.load(sys.stdin)
    except Exception as exc:
        return block(f"could not parse the tool payload ({exc}).")
    import _consent
    tool, ti = p.get("tool_name", ""), p.get("tool_input") or {}
    cdir = os.path.realpath(_consent.consent_dir())
    projects = os.path.realpath(os.path.expanduser("~/.claude/projects"))
    if tool in ("Write", "Edit", "NotebookEdit", "MultiEdit"):
        fp = ti.get("file_path") or ti.get("notebook_path") or ""
        rp = os.path.realpath(os.path.expanduser(fp)) if fp else ""
        if rp and (rp == cdir or rp.startswith(cdir + os.sep)):
            return block(f"{fp} is a consent file. Only the owner's own prompt creates one.")
        if rp.startswith(projects + os.sep) and rp.endswith(".jsonl"):
            return block(f"{fp} is a session transcript; it is never edited.")
        return 0
    if tool != "Bash":
        return 0
    cmd = ti.get("command", "") or ""
    if re.search(r"\bFACTORY_(?:STATE_DIR|ROOT)[\"']?\]?\s*=", cmd):
        return block("FACTORY_STATE_DIR and FACTORY_ROOT are the tests' overrides; a command may not set them. "
                     "Run the tests with `python3 -m unittest discover scripts/tests` (they set both themselves).")
    names = (cdir, _consent.consent_dir(), re.sub(r"^" + re.escape(os.path.expanduser("~")), "~", _consent.consent_dir()))
    for seg in re.split(r"&&|\|\||[;|\n]", cmd):
        if not any(n in seg for n in names) and not re.search(r"\.factory/[^\s/]+/consent", seg):
            continue
        if re.search(r"_consent\.py\s+(check|status)\b|scripts/consent\.py\s", seg) and ">" not in seg:
            continue
        words = seg.split()
        if not words or words[0] not in READ_ONLY or ">" in seg:
            return block("this command touches the consent directory. Consent comes from the owner's prompt only; "
                         "reading (ls, cat) and revoking (rm) are the only things a command may do there.")
    if re.search(r"\.claude/projects|transcript", cmd, re.I) and ".jsonl" in cmd and TRANSCRIPT_WRITE.search(cmd):
        return block("this command writes into a session transcript (.jsonl); transcripts are never edited.")
    for m in SEND_RUN.finditer(cmd):
        args = m.group(1)
        if "--help" in args or re.search(r"(^|\s)-h(\s|$)", args):
            continue
        d = re.search(r"--draft(?:-id)?[\s=]+(\S+)", args)
        did = d.group(1).strip("'\"") if d else None
        if not _consent.live("SEND", did):
            return block("scripts/send.py needs the owner's send instruction. " + _consent.refusal("SEND"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:   # a bug here must not stop all Bash; prod-guard and send.py check consent themselves
        print(f"consent-guard: internal error {exc!r}; passing", file=sys.stderr)
        sys.exit(0)
