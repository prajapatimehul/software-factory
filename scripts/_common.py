"""Shared helpers for the workflow scripts: paths, TSV ledgers, the mail CLI, text overlap.

Configuration comes from factory.conf through scripts/_conf.py only.
`python3 scripts/_common.py get KEY [default]` prints one value (the shell scripts use it)."""
import csv
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _conf  # noqa: E402

DEFAULTS = {"MAIL_CLI": "gws", "PROD_CONSENT_TOKEN": "PROD-WRITE-OK", "SEND_CONSENT_PHRASES": "send it|ok send",
            "CONSENT_TTL_MIN": "15", "MAX_REVIEW_ROUNDS": "3", "STATE_MAX_LINES": "150"}
BANNED_TO = ("no-reply@", "noreply@", "postmaster@", "do-not-reply@", "donotreply@")


def root():
    return str(_conf.root())


def conf(key, default=None):
    v = _conf.load().get(key)
    if v is None or v == "":
        v = DEFAULTS.get(key, "") if default is None else default
    return " ".join(v) if isinstance(v, (list, tuple)) else str(v)


def conf_list(key):
    return conf(key).split()


def conf_int(key):
    try:
        return int(conf(key))
    except ValueError:
        return int(DEFAULTS[key])


def path(*p):
    return os.path.join(root(), *p)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")


def today():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


# --- TSV ledgers -----------------------------------------------------------

def _clean(v):
    return str(v).replace("\t", " ").replace("\n", " ")


def _header(rel):
    with open(path(rel)) as f:
        return f.readline().rstrip("\n").split("\t")


def read_tsv(rel):
    with open(path(rel), newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def append_tsv(rel, row):
    header = _header(rel)
    # A file without a final newline would glue the new row onto the last one.
    with open(path(rel), "rb") as f:
        size = f.seek(0, 2)
        last = b""
        if size:
            f.seek(-1, 2)
            last = f.read(1)
    with open(path(rel), "a") as f:
        if size and last != b"\n":
            f.write("\n")
        f.write("\t".join(_clean(row.get(h, "")) for h in header) + "\n")


def rewrite_tsv(rel, rows):
    header = _header(rel)
    with open(path(rel), "w") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(_clean(r.get(h, "")) for h in header) + "\n")


def next_id(rel, col, prefix):
    """Ids come from here, never typed: the highest number in the column + 1."""
    n = 0
    for r in read_tsv(rel):
        m = re.match(prefix + r"-(\d+)", r.get(col, "") or "")
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}-{n + 1:03d}"


# --- mail CLI --------------------------------------------------------------

class MailUnavailable(Exception):
    pass


def mail_argv():
    argv = shlex.split(conf("MAIL_CLI"))
    if not argv:
        raise MailUnavailable("MAIL_CLI is empty in factory.conf")
    # "env VAR=x gws" is allowed, so look for the first word that is a program.
    prog = next((a for a in argv if a != "env" and "=" not in a), argv[0])
    if not (shutil.which(prog) or os.path.exists(prog)):
        raise MailUnavailable(f"MAIL_CLI program {prog!r} not found")
    return argv


def mail(*args, timeout=60):
    """Run MAIL_CLI with gws-style arguments (`gmail users drafts create --params … --json …`) and return its JSON.
    Another mail tool works if a small wrapper script accepts the same arguments."""
    argv = mail_argv()
    try:
        out = subprocess.run([*argv, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise MailUnavailable(f"MAIL_CLI failed to run: {e}")
    if out.returncode != 0:
        raise MailUnavailable(f"MAIL_CLI failed: {out.stderr.strip()[:400]} (auth expired? the owner logs in again)")
    try:
        return json.loads(out.stdout) if out.stdout.strip() else {}
    except ValueError:
        raise MailUnavailable(f"MAIL_CLI did not print JSON: {out.stdout[:200]!r}")


def mail_or_die(*args, **kw):
    try:
        return mail(*args, **kw)
    except MailUnavailable as e:
        die(f"REFUSED: {e}")


def my_address():
    """The mailbox the mail CLI is logged in to. OWNER_EMAIL in factory.conf (optional) saves the call."""
    own = conf("OWNER_EMAIL", "")
    if own:
        return own.lower()
    try:
        return (mail("gmail", "users", "getProfile", "--params", json.dumps({"userId": "me"})).get("emailAddress") or "").lower()
    except MailUnavailable:
        return ""


def addresses(v):
    return re.findall(r"[\w.+-]+@[\w.-]+\w", v or "")


def is_client_address(addr):
    """CLIENT_CONTACT_EMAILS entries are full addresses or '@domain' suffixes."""
    a = addr.lower()
    return any(a == c.lower() or (c.startswith("@") and a.endswith(c.lower())) for c in conf_list("CLIENT_CONTACT_EMAILS"))


# --- text ------------------------------------------------------------------

def normalise(text):
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", text.lower())).strip()


def overlap(a, b):
    A, B = set(normalise(a).split()), set(normalise(b).split())
    return len(A & B) / max(1, len(A | B))


def consent_module():
    """The consent helper the hooks own (.claude/hooks/_consent.py), or None. Callers fail closed on None."""
    # Next to this file, not under root(): the hooks are code, and FACTORY_ROOT only moves the data.
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude", "hooks"))
    try:
        import _consent
        return _consent
    except Exception:
        return None


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "get":
        print(conf(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
    elif len(sys.argv) == 2 and sys.argv[1] == "root":
        print(root())
    else:
        die(__doc__)
