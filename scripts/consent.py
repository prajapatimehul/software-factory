#!/usr/bin/env python3
"""Consent from an answered question: the second path next to the owner's own prompt.

An answer the owner picks in an AskUserQuestion dialog never arrives as a prompt, so the consent hook cannot see it.
This script is the only way such an answer becomes consent:

  consent.py from-ask PROD|SEND|REVIEW-ROUNDS-OK [--draft ID] [--transcript PATH]
  consent.py status

from-ask reads the current session transcript (main thread only, not a subagent), takes the newest answered question
no older than CONSENT_TTL_MIN, and writes the consent record only when the ANSWER carries it:
  PROD              the answer names PROD_CONSENT_TOKEN (an option label such as "<token>: run the migration")
  SEND              the answer starts with "send" or one of SEND_CONSENT_PHRASES
  REVIEW-ROUNDS-OK  the answer names REVIEW-ROUNDS-OK (one more review round past MAX_REVIEW_ROUNDS)
The question text alone never counts: a "yes" to some other question is not consent. Each answer is used once."""
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import conf, conf_int, consent_module  # noqa: E402

ROUNDS = "REVIEW-ROUNDS-OK"
NOT_CONSENT = re.compile(r"\b(needs?|needed|requires?|required|without|no|not|never|don'?t|do not|wait(?:ing)? for)\b", re.I)


def die(msg):
    print(f"consent: REFUSED - {msg}", file=sys.stderr)
    sys.exit(1)


def token_re(word):
    """'PROD-WRITE-OK', 'prod write ok' and 'prod_write_ok' are the same word."""
    parts = [re.escape(p) for p in re.split(r"[\s_-]+", word) if p]
    return re.compile(r"(?<![\w-])" + r"[\s_-]*".join(parts) + r"(?![\w-])", re.I)


def transcript_path(arg=None):
    if arg:
        return arg
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not re.fullmatch(r"[0-9a-f-]{36}", sid):
        die("CLAUDE_CODE_SESSION_ID is not set; run this from the session that asked the question")
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
    if not hits:
        die(f"no transcript for session {sid}")
    return hits[0]


def answers(path):
    """[(timestamp, tool_use_id, question, answer)] for answered AskUserQuestion calls on the main thread."""
    asked, out = {}, []
    for ln in open(path, encoding="utf-8", errors="ignore"):
        if "AskUserQuestion" not in ln and "toolUseResult" not in ln:
            continue
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(o, dict) or o.get("isSidechain"):
            continue
        content = (o.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if o.get("type") == "assistant" and b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion":
                asked[b.get("id")] = True
            if o.get("type") == "user" and b.get("type") == "tool_result" and b.get("tool_use_id") in asked:
                tur = o.get("toolUseResult") if isinstance(o.get("toolUseResult"), dict) else {}
                ans = tur.get("answers") or {}
                if isinstance(ans, dict):
                    for q, a in ans.items():
                        out.append((o.get("timestamp", ""), b["tool_use_id"], str(q), str(a)))
    return out


def carries(token, answer, draft, draft_re):
    """(ok, draft ids named) — does this answer give the consent?"""
    if answer.rstrip().endswith("?"):
        return False, []
    if token == "SEND":
        phrases = [re.escape(p.strip()).replace(r"\ ", r"\s+") for p in conf("SEND_CONSENT_PHRASES").split("|") if p.strip()]
        ok = bool(re.match(r"^\s*(?:(?:yes|ok(?:ay)?|please)[\s,.!]+)*(?:send\b|" + "|".join(phrases or ["send it"]) + ")", answer, re.I))
        drafts = sorted(set(draft_re.findall(answer))) if draft_re else []
        if ok and draft and drafts and draft not in drafts:
            ok = False
        return ok, drafts
    word = conf("PROD_CONSENT_TOKEN") if token == "PROD" else ROUNDS
    m = token_re(word).search(answer)
    return bool(m) and not NOT_CONSENT.search(answer[:m.start()]), []


def main(argv):
    c = consent_module()
    if c is None:
        die("the consent helper (.claude/hooks/_consent.py) is missing")
    if argv[:1] == ["status"]:
        rc = c.main(["status"])
        rec = c.live(ROUNDS)
        print(f"{ROUNDS}: " + (f"live until {rec['expires']}: {rec['excerpt'][:100]}" if rec else "none"))
        return rc
    if len(argv) < 2 or argv[0] != "from-ask":
        print(__doc__, file=sys.stderr)
        return 2
    token = "PROD" if argv[1] in ("PROD", conf("PROD_CONSENT_TOKEN")) else argv[1]
    if token not in ("PROD", "SEND", ROUNDS):
        print(__doc__, file=sys.stderr)
        return 2
    draft = argv[argv.index("--draft") + 1] if "--draft" in argv else None
    path = transcript_path(argv[argv.index("--transcript") + 1] if "--transcript" in argv else None)
    ttl = conf_int("CONSENT_TTL_MIN")
    now = datetime.datetime.now(datetime.timezone.utc)
    fresh = []
    for ts, tid, q, a in answers(path):
        try:
            t = datetime.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
        if datetime.timedelta(0) <= now - t <= datetime.timedelta(minutes=ttl):
            fresh.append((t, tid, q, a))
    owner = conf("OWNER_NAME") or "the owner"
    if not fresh:
        die(f"no question was answered in the last {ttl} min in {path}. Ask {owner} with an option that names the consent.")
    os.makedirs(c.consent_dir(), mode=0o700, exist_ok=True)
    used_f = os.path.join(c.consent_dir(), "used-asks.txt")
    used = set(open(used_f).read().split()) if os.path.exists(used_f) else set()
    for t, tid, q, a in sorted(fresh, reverse=True):
        ok, drafts = carries(token, a, draft, getattr(c, "DRAFT_ID", None))
        if not ok:
            continue
        key = f"{tid}:{token}"
        if key in used:
            die(f"the answer {tid} was already used for {token}; ask {owner} again")
        c.write(token, f"Q: {q[:120]} A: {a[:110]}", f"ask:{tid}", os.environ.get("CLAUDE_CODE_SESSION_ID", ""), drafts)
        with open(used_f, "a") as f:
            f.write(key + "\n")
        rec = c.live(token) or {}
        print(f"consent: {token} recorded from the answer {a[:80]!r} ({tid}), live until {rec.get('expires', '?')}")
        return 0
    die(f"the newest answer {sorted(fresh, reverse=True)[0][3][:80]!r} does not carry {token}. The answer itself must "
        "name it (an option label the owner picks, or their own text).")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
