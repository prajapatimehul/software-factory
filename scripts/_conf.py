"""The one reader of factory.conf. Every hook and script goes through load() and root().

factory.conf is shell-style: KEY=VALUE, optional quotes, # comments. A key that is missing or empty
takes its default below, so a half-filled file never yields an empty consent token.
"""
import os
import re
from pathlib import Path

DEFAULTS = {
    "CLIENT_NAME": "",
    "CLIENT_SLUG": "",
    "OWNER_NAME": "",
    "CLIENT_REPOS": "",
    "CLIENT_CONTACT_EMAILS": "",
    "MAIL_CLI": "gws",
    "PROD_MARKERS": "",
    "DEV_MARKERS": "",
    "PROD_CONSENT_TOKEN": "PROD-WRITE-OK",
    "SEND_CONSENT_PHRASES": "send it|ok send",
    "CONSENT_TTL_MIN": "15",
    "MAX_REVIEW_ROUNDS": "3",
    "STATE_MAX_LINES": "150",
    # Optional: extra words that must never be written into a client repo (client-repo-guard).
    "PRIVATE_WORDS": "timesheet billable do-not-chase",
}

_LINE = re.compile(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*)$")


def root() -> Path:
    """The repo root: $FACTORY_ROOT (tests), else the nearest parent of this file holding factory.conf."""
    env = os.environ.get("FACTORY_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for d in here.parents:
        if (d / "factory.conf").is_file():
            return d
    return here.parent.parent


def load() -> dict:
    conf = dict(DEFAULTS)
    try:
        lines = (root() / "factory.conf").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        m = _LINE.match(line)
        if not m or line.lstrip().startswith("#"):
            continue
        value = m.group(2).strip()
        if value[:1] in ('"', "'") and value.find(value[0], 1) > 0:
            value = value[1:value.find(value[0], 1)]
        else:
            value = re.sub(r"(^|\s)#.*$", "", value).strip()
        if value or m.group(1) not in DEFAULTS:
            conf[m.group(1)] = value
    return conf


def words(key: str, conf: dict = None) -> list:
    """A space-separated value as a list."""
    return (conf or load()).get(key, "").split()


def number(key: str, conf: dict = None) -> int:
    try:
        return int((conf or load()).get(key, ""))
    except ValueError:
        return int(DEFAULTS[key])


def repos(conf: dict = None) -> list:
    """CLIENT_REPOS as resolved paths (entries are relative to the repo root)."""
    base = root()
    return [(base / os.path.expanduser(r)).resolve() for r in words("CLIENT_REPOS", conf)]


def state_dir(conf: dict = None) -> Path:
    """Per-machine state outside the repo: consent files, the evidence log, gate logs.
    $FACTORY_STATE_DIR moves it for tests only; consent-guard refuses it in a command."""
    env = os.environ.get("FACTORY_STATE_DIR")
    if env:
        return Path(env)
    slug = (conf or load()).get("CLIENT_SLUG") or root().name
    return Path.home() / ".factory" / re.sub(r"[^A-Za-z0-9_.-]", "_", slug)
