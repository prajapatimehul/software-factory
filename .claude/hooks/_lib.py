"""Shared code for the hooks: config, the hook payload, deny/warn, and the token and claim rules.

Evidence is what this session's tools printed and what the owner typed. evidence-log.py records it per
session under the state directory, so the gates can tell a copied number from a typed one."""
import json
import os
import re
import sys

# realpath: .claude may be reached through a symlink, and the scripts directory is found from here.
HOOKS = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HOOKS, "..", "..", "scripts"))
import _conf  # noqa: E402

CONF = _conf.load()
ROOT = str(_conf.root())
STATE = str(_conf.state_dir(CONF))
EVID = os.path.join(STATE, "evidence")
OWNER = CONF.get("OWNER_NAME") or "the owner"


# --- payload and answers -----------------------------------------------------

def read_payload():
    try:
        return json.load(sys.stdin)
    except Exception:
        return None


def deny(reason):
    """PreToolUse: refuse the call; the reason goes back to the model."""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


def context(event, text):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))


def gate_mode(name, default="warn"):
    """deny | warn | off, from .claude/gates.conf."""
    try:
        with open(os.path.join(ROOT, ".claude", "gates.conf")) as f:
            for line in f:
                k, _, v = line.split("#")[0].strip().partition("=")
                if k.strip() == name and v.strip() in ("warn", "deny", "off"):
                    return v.strip()
    except OSError:
        pass
    return default


def warn(hook, session_id, reason):
    """warn mode: log what deny mode would have refused. session-start.py prints the count."""
    os.makedirs(STATE, exist_ok=True)
    with open(os.path.join(STATE, "gate-warnings.log"), "a") as f:
        f.write(f"{hook}\t{session_id}\t{reason.replace(chr(10), ' ')}\n")
    sys.exit(0)


def gate(name, payload, reason, default="warn"):
    mode = gate_mode(name, default)
    if mode == "deny":
        deny(reason)
    if mode == "warn":
        warn(name, payload.get("session_id"), reason)


# --- files -------------------------------------------------------------------

def rel_path(file_path):
    """Path relative to the repo root, or None when the file is outside it."""
    try:
        rp, root = os.path.realpath(file_path), os.path.realpath(ROOT)
        if rp.startswith(root + os.sep):
            return os.path.relpath(rp, root)
    except Exception:
        pass
    return None


def new_text(tool_name, tool_input):
    """The text a Write/Edit adds: the whole content for Write, the new lines for Edit."""
    if tool_name == "Write":
        return tool_input.get("content", "") or ""
    if tool_name == "Edit":
        old = set((tool_input.get("old_string", "") or "").split("\n"))
        return "\n".join(l for l in (tool_input.get("new_string", "") or "").split("\n") if l not in old)
    return ""


def file_text(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def response_text(payload):
    """A tool response as plain text: every string and number inside it, one per line. json.dumps would turn a
    newline into the two characters \\n, and then "\\n4821" no longer reads as the number 4821."""
    def walk(v):
        if isinstance(v, str):
            return [v]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return [str(v)]
        if isinstance(v, dict):
            v = list(v.values())
        return [s for x in v for s in walk(x)] if isinstance(v, list) else []
    return "\n".join(walk(payload.get("tool_response")))


def read_tsv(rel):
    import csv
    try:
        with open(os.path.join(ROOT, rel), newline="") as f:
            return list(csv.DictReader(f, delimiter="\t"))
    except OSError:
        return []


# --- numbers and ids ---------------------------------------------------------

# Our own ids, dates and years are not evidence tokens: T-029, P4, #12, "step 3", 2026.
STRIP = re.compile(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?Z?)?"
                   r"|\b[A-Z]{1,3}-?\d{1,4}[a-z]?\b"
                   r"|#\d+\b"
                   r"|\b(?:mistake|learning|entry|entries|item|items|step|steps|rule|round|phase|part|section|§|hook)\s*\d+[a-z]?\b"
                   r"|\b(?:19|20)\d{2}\b", re.I)
ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}(?::\d{2})?)Z?")
CLASSES = {
    "time": re.compile(r"(?<![\w:])\d{1,2}:\d{2}(?::\d{2})?Z?(?![\w:])"),
    "uuid": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    "hexid": re.compile(r"\b[0-9a-f]{7,40}\b"),
    "decimal": re.compile(r"(?<![\w.])\d[\d,]*\.\d+(?![\w.])"),
    "integer": re.compile(r"(?<![\w.,:-])(?:\d{1,3}(?:,\d{3})+|\d{2,})(?![\w.,:-])"),
}


def tokens(text):
    """[(class, original, normalised)] for every time, id, decimal and integer of two or more digits."""
    out = [("time", m.group(1), m.group(1)) for m in ISO_TIME.finditer(text)]
    text = STRIP.sub(" ", text)
    for cls, rx in CLASSES.items():
        for m in rx.finditer(text):
            t = m.group(0)
            if cls == "hexid" and (t.isdigit() or t.isalpha()):
                continue
            out.append((cls, t, t.replace(",", "").rstrip("Z")))
    return out


def evidence_forms(text):
    """Every normalised token in text, plus HH:MM for each HH:MM:SS (a minute-precision copy is a copy)."""
    forms = set()
    for cls, _, n in tokens(text):
        forms.add(n)
        if cls == "time" and n.count(":") == 2:
            forms.add(n.rsplit(":", 1)[0])
    return forms


def unmatched_tokens(text, known):
    out = []
    for _, o, n in tokens(text):
        if n in known or (n.count(":") == 1 and any(k.startswith(n + ":") for k in known)):
            continue
        if o not in [x[0] for x in out]:
            out.append((o, n))
    return out


def session_files(session_id):
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")
    os.makedirs(EVID, mode=0o700, exist_ok=True)
    return os.path.join(EVID, sid + ".log"), os.path.join(EVID, sid + ".tokens")


def evidence_set(session_id):
    return set(file_text(session_files(session_id)[1]).split())


# --- claims ------------------------------------------------------------------

CLAIM = re.compile(r"\b(works|working now|fixed|tested|done|runs now|is empty|is missing|blocked|cannot|can't|not possible|"
                   r"verified|confirmed|deleted|restored|live|clean|identical|no path|absent|none|zero|passed|succeeded|"
                   r"unchanged|completed?|all of them|every one of them|nothing (?:else|to do|left)|in place|is up|are up|"
                   r"is running|are running|healthy|no errors?|no failures?|resolved|released|merged|deployed)\b", re.I)
EVIDENCE = re.compile(r"\bcmd:|`[^`]{3,}`\s*(?:→|->|=>|⇒|=|gave|returned|printed|shows|showed|says|said)"
                      r"|\bexit(?:ed)?\s*(?:code)?\s*=?\s*\d|\b(?:stdout|output):", re.I)
EXEMPT = re.compile(r"^\s*(#|\|?\s*-{3,}|-?\s*\*{0,2}(Next|Open|TODO|Plan|Not verified|Unverified)\b)|\?\s*$"
                    r"|\bnot (?:yet )?(?:checked|verified|confirmed|tested|done)\b|\bunverified\b", re.I)


def unsupported_claims(lines):
    """Lines that make a claim with no command on the line before or within the three after."""
    bad = []
    for i, line in enumerate(lines):
        if not CLAIM.search(line) or EXEMPT.search(line):
            continue
        if EVIDENCE.search("\n".join(lines[max(0, i - 1): i + 4])):
            continue
        bad.append(line.strip()[:110])
    return bad
