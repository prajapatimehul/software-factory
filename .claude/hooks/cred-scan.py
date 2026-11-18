#!/usr/bin/env python3
"""A secret never lands in a session transcript. Masking is not enough on its own: a mask written for
`password=` does not match a `password <value>` line, so the file is refused before it is printed.

PreToolUse (Bash, Read, Grep): refuse printing a credentials file: cat/head/tail/less/grep/jq/awk/sed/base64 ...
  (and `< file`, the Read tool, the Grep tool) on ~/.aws/credentials*, *.pem / *.key / *.p12 / *.token, ssh private
  keys, client_secret*.json, token*.json under ~/.config, and .env files (not .env.example / .sample / .template).
  Passes: a pipeline whose sed replaces the value with <hidden>, a count/quiet/list grep (-c -q -l), and a read
  inside $( ... ) that feeds a variable. Fails closed on an unparseable payload.
PostToolUse (Bash, Read, Grep): scan the output for secret shapes and add context: a secret was printed, do not
  repeat it, rotate it, record the mistake. The hook names the kind, never the value. Hits are logged (kind only)
  to <state dir>/cred-scan.log."""
import datetime
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import STATE, response_text  # noqa: E402

HOME = os.path.expanduser("~")
READERS = {"cat", "head", "tail", "less", "more", "bat", "grep", "egrep", "fgrep", "rg", "nl", "strings", "xxd", "od",
           "hexdump", "base64", "jq", "awk", "gawk", "sed", "tac", "column", "cut", "sort", "uniq", "diff", "cmp"}
MASK_SED = re.compile(r"\bsed\b[^|;&]*<hidden>")
QUIET_GREP = re.compile(r"^(?:e|f)?grep\b.*\s-\w*[cqlL]|^rg\b.*\s-\w*[clq]")
SUBST = re.compile(r"\$\((?:[^()]|\([^()]*\))*\)")

SHAPES = [
    ("AWS secret key", re.compile(r"(?i)(?:aws_secret_access_key|SecretAccessKey)\W{1,6}[A-Za-z0-9/+=]{40}")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_\w{30,})")),
    ("Google OAuth client secret", re.compile(r"\bGOCSPX-[\w-]{20,}")),
    ("Slack token", re.compile(r"\bxox[baprs]-[\w-]{10,}")),
    ("API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("password line", re.compile(r"(?im)^\W{0,3}(?:password|passwd|pwd|secret|api[_-]?key)\W{0,3}\s*[:= ]\s*[\"']?"
                                 r"(?!<hidden>|\*{3}|x{3}|changeme|example|\$\{|\$\(|(?:string|str|none|null|true|false|undefined)\b)[^\s\"'<>(){}]{6,}[\"']?\s*$")),
]


def is_cred_path(p):
    p = os.path.normpath(p)
    base = os.path.basename(p)
    if re.fullmatch(r"credentials(\..*)?", base) and os.sep + ".aws" + os.sep in p:
        return True
    if re.search(r"\.(key|pem|p12|pfx|token)$", base) or re.fullmatch(r"id_(rsa|ed25519|ecdsa|dsa)", base):
        return True
    if re.fullmatch(r"client_secret.*\.json", base) or (os.sep + ".config" + os.sep in p and re.fullmatch(r"token.*\.json", base)):
        return True
    return bool(re.fullmatch(r"\.env(\.(?!example$|sample$|template$|dist$)[\w.-]+)?", base))


def expand(tok, cwd):
    tok = tok.replace("${HOME}", HOME).replace("$HOME", HOME)
    if tok.startswith("~"):
        tok = HOME + tok[1:]
    return tok if os.path.isabs(tok) else os.path.join(cwd, tok)


def cred_reads(cmd, cwd):
    """Credential files a Bash command would print. A `cd DIR` moves where later relative paths resolve."""
    hits, cwd = [], cwd or os.getcwd()
    for pipeline in re.split(r"&&|\|\||;|\n", SUBST.sub(" ", cmd)):
        masked = bool(MASK_SED.search(pipeline))
        for seg in pipeline.split("|"):
            try:
                words = shlex.split(seg)
            except ValueError:
                words = seg.split()
            while words and (re.match(r"^\w+=", words[0]) or words[0] in ("sudo", "command", "env")):
                words = words[1:]
            if not words:
                continue
            if words[0] in ("cd", "pushd") and len(words) > 1:
                cwd = expand(words[1], cwd)
                continue
            redirected = [m.group(1) for m in re.finditer(r"<\s*([^\s<>|&;]+)", seg)]
            reads = words[1:] if os.path.basename(words[0]) in READERS else []
            if masked or QUIET_GREP.search(" ".join(words)):
                continue
            hits += [w for w in reads + redirected if not w.startswith("-") and is_cred_path(expand(w.strip("'\""), cwd))]
    return hits


def pre(payload):
    tool, ti = payload.get("tool_name"), payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()
    if tool == "Bash":
        hits = cred_reads(ti.get("command", "") or "", cwd)
    else:
        target = ti.get("file_path") or ti.get("path") or ""
        hits = [target] if target and is_cred_path(expand(target, cwd)) else []
    if hits:
        print(f"cred-scan: BLOCKED - this would print a credentials file into the transcript ({os.path.basename(hits[0])}). "
              "Use the value without printing it (read it inside $( ... ) into a variable), or mask it "
              "(`sed 's/=.*/=<hidden>/'`), or count it (`grep -c`).", file=sys.stderr)
        return 2
    return 0


def post(payload):
    text = response_text(payload)[:5_000_000]
    kinds = [kind for kind, rx in SHAPES if rx.search(text)]
    if not kinds:
        return 0
    try:
        os.makedirs(STATE, exist_ok=True)
        with open(os.path.join(STATE, "cred-scan.log"), "a") as f:
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            f.write(f"{ts}\t{payload.get('session_id')}\t{payload.get('tool_name')}\t{', '.join(kinds)}\n")
    except Exception:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
          f"cred-scan: the output above contains what looks like a secret ({', '.join(kinds)}). Do not repeat, quote or "
          "write the value anywhere. Tell the owner it was printed so it can be rotated, and record the mistake."}}))
    return 0


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(f"cred-scan: could not parse the tool payload ({exc}); refusing.", file=sys.stderr)
        return 2
    if payload.get("tool_name") not in ("Bash", "Read", "Grep"):
        return 0
    return post(payload) if payload.get("hook_event_name") == "PostToolUse" else pre(payload)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
