#!/usr/bin/env python3
"""Consent with human provenance. The production token and a send instruction count only when the owner
typed them, not when the model typed the word into a command.

consent-capture.py (UserPromptSubmit) is the only writer: it calls detect() on the owner's own prompt text
and write() for what it finds. Files: <state dir>/consent/PROD.json and SEND.json
{token, excerpt, created, expires, source, session_id, draft_ids}, live for CONSENT_TTL_MIN minutes.
The gates still need the token in the command AND a live file.

Token names: "PROD" (or the configured PROD_CONSENT_TOKEN itself), "SEND", and "REVIEW-ROUNDS-OK" (one more
review round past MAX_REVIEW_ROUNDS; its own word, so one yes never opens two doors).

CLI:  _consent.py check TOKEN [--draft ID]   exit 0 = live consent, 1 = none (any error = none)
      _consent.py status                     print live consents
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "scripts"))
import _conf  # noqa: E402

CONF = _conf.load()
PROD_TOKEN = CONF["PROD_CONSENT_TOKEN"]
TOKENS = ("PROD", "SEND")
TTL_MIN = _conf.number("CONSENT_TTL_MIN", CONF)
OWNER = CONF.get("OWNER_NAME") or "the owner"

# Blocks inside a prompt that the owner did not type: task results, other sessions, pasted text.
FOREIGN = re.compile(r"<(task-notification|cross-session-message|teammate-message|pasted_content|system-reminder)\b[^>]*>.*?</\1>",
                     re.S | re.I)
FOREIGN_MARKERS = ("<task-notification", "[SYSTEM NOTIFICATION", "<cross-session-message", "<teammate-message", "<pasted_content")
# "It needs a PROD-WRITE-OK for each step" describes the token; it does not give it.
NOT_CONSENT = re.compile(r"\b(needs?|needing|needed|require[sd]?|requiring|without|no|not|never|don'?t|do not|ask(?:ed|ing)?|"
                         r"wait(?:ing)? for)\b", re.I)
# "prod-write-ok", "PROD WRITE OK" and "prod_write_ok" are the same word.
def _word(token):
    return re.compile(r"(?<![\w-])" + r"[\s_-]*".join(re.escape(p) for p in re.split(r"[\s_-]+", token) if p) + r"(?![\w-])", re.I)


WORDS = {"PROD": _word(PROD_TOKEN), "REVIEW-ROUNDS-OK": _word("REVIEW-ROUNDS-OK")}
# A send instruction is a line that STARTS with one of the phrases (or /send), after an optional "ok", "yes", "please".
_PHRASES = [re.escape(p.strip()).replace(r"\ ", r"\s+") for p in CONF["SEND_CONSENT_PHRASES"].split("|") if p.strip()]
SEND_LINE = re.compile(r"^\s*(?:(?:ok(?:ay)?|yes|yep|yeah|sure|go ahead(?: and)?|please|pls|then|now|and|so)[\s,.!]+)*"
                       r"(?:/send\b|(?:" + "|".join(_PHRASES or ["send it"]) + r")\b)", re.I)
SEND_CMD_TAG = re.compile(r"<command-name>\s*/?send\s*</command-name>", re.I)
DRAFT_ID = re.compile(r"\b(?:[A-Za-z]{1,3}-?\d{6,}|[0-9a-f]{12,})\b")


def canonical(token):
    return "PROD" if token in ("PROD", PROD_TOKEN) else token


def consent_dir() -> str:
    return os.path.join(str(_conf.state_dir(CONF)), "consent")


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def human_text(prompt: str) -> str:
    """The part of a prompt the owner typed: foreign blocks and quoted ('> ') lines removed."""
    if not prompt:
        return ""
    t = FOREIGN.sub("", prompt)
    if any(m in t for m in FOREIGN_MARKERS):   # an unclosed foreign block: trust nothing in this prompt
        return ""
    return "\n".join(ln for ln in t.splitlines() if not ln.lstrip().startswith(">"))


def detect(text: str) -> dict:
    """{token: (excerpt, draft_ids)} for the consents carried by already-cleaned human text."""
    out = {}
    lines = text.splitlines()
    for tok, rx in WORDS.items():
        for ln in lines:
            m = rx.search(ln)
            if m and not NOT_CONSENT.search(ln[:m.start()]) and not ln.rstrip().endswith("?"):
                out[tok] = (ln.strip()[:240], [])
                break
    sends = []
    for ln in lines:
        m = SEND_LINE.search(ln)
        if m and not ln.rstrip().endswith("?") and not NOT_CONSENT.search(ln[:m.end()]):
            sends.append(ln.strip())
    if SEND_CMD_TAG.search(text):
        sends.append(text.strip()[:240])
    if sends:
        out["SEND"] = (" | ".join(sends)[:240], sorted(set(DRAFT_ID.findall(" ".join(sends)))))
    return out


def write(token: str, excerpt: str, source: str = "prompt", session_id: str = "", draft_ids=None) -> str:
    token = canonical(token)
    d = consent_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    t = now()
    rec = {"token": token, "excerpt": excerpt, "created": _iso(t), "expires": _iso(t + datetime.timedelta(minutes=TTL_MIN)),
           "source": source, "session_id": session_id or "", "draft_ids": list(draft_ids or [])}
    path = os.path.join(d, f"{token}.json")
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=1)
    os.replace(tmp, path)
    return path


def live(token: str, draft_id: str = None):
    """The live consent record for token (and draft id, when the record names drafts), else None. Never raises."""
    try:
        token = canonical(token)
        with open(os.path.join(consent_dir(), f"{token}.json")) as f:
            rec = json.load(f)
        if rec.get("token") != token:
            return None
        created, expires, t = _parse(rec["created"]), _parse(rec["expires"]), now()
        # A hand-made file with a far expiry or a future creation time is not live either.
        if not (created - datetime.timedelta(seconds=60) <= t < expires):
            return None
        if expires - created > datetime.timedelta(minutes=TTL_MIN, seconds=5):
            return None
        if draft_id and rec.get("draft_ids") and draft_id not in rec["draft_ids"]:
            return None
        return rec
    except Exception:
        return None


def refusal(token: str) -> str:
    what = f"{PROD_TOKEN}" if canonical(token) == "PROD" else "A send instruction"
    return (f"{what} counts only when {OWNER} typed it in their own prompt within the last {TTL_MIN} min "
            f"(consent-capture.py records it). The same word typed by the agent or a script does not count. "
            f"Ask {OWNER}; do not retry.")


def main(argv) -> int:
    if len(argv) >= 2 and argv[0] == "check":
        draft = argv[argv.index("--draft") + 1] if "--draft" in argv else None
        return 0 if live(argv[1], draft) else 1
    if argv[:1] == ["status"]:
        for tok in TOKENS:
            rec = live(tok)
            name = PROD_TOKEN if tok == "PROD" else tok
            print(f"{name}: " + (f"live until {rec['expires']}: {rec['excerpt'][:100]}" if rec else "none"))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        sys.exit(1)
