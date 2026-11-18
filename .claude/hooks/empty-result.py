#!/usr/bin/env python3
"""PostToolUse on Bash. When a query-like command printed nothing, or a bare count of 0, a reminder lands at the
moment the mistake is made: an empty result is not evidence of absence until a must-match control (the same
command on a value known to exist) has printed something. Names hidden stderr. Adds context only. RULES.md P5."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import context, read_payload

EMPTYISH = {"", "0", "[]", "{}", "()", "none", "null", "nil", "false"}
SILENT = re.compile(r"^\s*(?:sudo\s+)?(?:mkdir|cp|mv|rm|touch|chmod|chown|ln|export|cd|kill|sleep|printf|echo|tee|true|set|"
                    r"unset|source|\.|git\s+(?:add|commit|push|pull|fetch|checkout|switch|stash|mv|rm|reset|tag|branch\s+-[dD])|"
                    r"sed\s+-i|cat\s*>|wait|trap)\b")
QUERY = re.compile(r"\b(?:grep|rg|ag|find|ls|aws|gcloud|az|kubectl|curl|wget|dig|jq|wc|python3?|sqlite3|psql|mysql|node|gh|cat|"
                   r"head|tail|sort|uniq|search|list|describe|get|filter|lookup|select|show|query|stat|du|df|ps|lsof|"
                   r"git\s+(?:log|grep|show|diff|status|ls-files|rev-list|branch))\b")
ZERO_TAIL = re.compile(r"(?:^|[^0-9.,])0\s*$")


def main():
    p = read_payload()
    if not p or p.get("tool_name") != "Bash":
        return
    cmd = (p.get("tool_input") or {}).get("command", "") or ""
    tr = p.get("tool_response")
    stdout = tr if isinstance(tr, str) else (tr.get("stdout", "") or "") if isinstance(tr, dict) else ""
    stderr = (tr.get("stderr", "") or "") if isinstance(tr, dict) else ""
    if stderr.strip():
        return   # a failed command is an error, not an empty result
    segments = [s for s in re.split(r"&&|\|\||;|\n", cmd) if s.strip()]
    if (segments and all(SILENT.match(s) for s in segments)) or not QUERY.search(cmd):
        return
    out = stdout.strip()
    last = out.splitlines()[-1].strip() if out else ""
    if out.lower() in EMPTYISH:
        what = "printed nothing" if not out else f"printed only {out!r}"
    elif ZERO_TAIL.search(last) and len(last) < 80:
        what = f"ended with a count of 0 ({last!r})"
    else:
        return
    hidden = " Its stderr was hidden by 2>/dev/null, so a failed command looks the same as an empty one." if "2>/dev/null" in cmd else ""
    context("PostToolUse", f"empty-result: this command {what}. That is not evidence of absence until a must-match control "
            f"(the same command with a value known to exist) prints something.{hidden} Before writing none / absent / "
            "empty / 0 into a file, run the control and keep both outputs. (RULES.md P5)")


try:
    main()
except Exception:
    pass
sys.exit(0)
