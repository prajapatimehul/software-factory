#!/usr/bin/env python3
"""PreToolUse on Bash: mail is written only by scripts/draft.py (creates a draft) and scripts/send.py (after the
owner's send instruction). A raw MAIL_CLI write, or a direct sender (sendmail, msmtp, mutt, smtp://), is refused.
The wrappers hold the ledger checks that stop a repeated ask; a raw write skips them."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import CONF, OWNER, read_payload

DIRECT = re.compile(r"(?:^|[;&|(\s])(?:sendmail|msmtp|mailx|mutt|swaks)\s|(?:^|[;&|(\s])mail\s+-s\b|\bsmtps?://")
# A write is a resource word followed by a write verb ("drafts create", "message send"); a search query that
# happens to contain "update" is not one.
WRITE = re.compile(r"\b(?:gmail|mail|messages?|drafts?|threads?|envelopes?|labels|settings)\s+(?:send|insert|import|modify|"
                   r"trash|untrash|delete|batchModify|batchDelete|create|update|patch|reply|forward|write|move|copy)\b", re.I)
ROUTED = re.compile(r"scripts/(?:draft|send)\.py\b")


def main():
    p = read_payload()
    if p is None:
        print("mail-guard: could not parse the tool payload; refusing.", file=sys.stderr)
        sys.exit(2)
    if p.get("tool_name") != "Bash":
        return
    cmd = (p.get("tool_input") or {}).get("command", "") or ""
    # "env VAR=x gws" and "gws --flag" are both allowed: the program is the first word that is neither.
    words = (CONF.get("MAIL_CLI") or "gws").split()
    cli = next((w for w in words if w != "env" and "=" not in w), words[-1])
    cli_rx = re.compile(r"(?:^|[;&|(\s/])" + re.escape(os.path.basename(cli)) + r"(?:\s|$)")
    for seg in re.split(r"&&|\|\||;|\n", cmd):
        if ROUTED.search(seg):
            continue
        raw = cli_rx.search(seg) and WRITE.search(seg)
        if raw or DIRECT.search(seg):
            print("mail-guard: mail writes go through scripts/draft.py (creates a draft) or scripts/send.py "
                  f"(after {OWNER} says to send). Raw mail writes are refused; reads pass.", file=sys.stderr)
            sys.exit(2)


try:
    main()
except SystemExit:
    raise
except Exception:   # permissions.deny in settings.json is the backstop
    pass
sys.exit(0)
