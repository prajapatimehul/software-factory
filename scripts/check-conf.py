#!/usr/bin/env python3
"""Check THIS fork's factory.conf. The unit tests run on a fixture and never read it; this does.

  check-conf.py          exit 1 on a FAIL line, 0 otherwise

FAIL: a key the guards cannot work without is empty, or still holds a value the template shipped with.
WARN: something to look at that a guard cannot decide for you. Reads files only; no network."""
import os
import re
import shlex
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _conf  # noqa: E402

PLACEHOLDER = re.compile(r"acme|000000000000|111111111111|\.example\b", re.I)
REQUIRED = ("CLIENT_NAME", "CLIENT_SLUG", "OWNER_NAME", "CLIENT_REPOS", "CLIENT_CONTACT_EMAILS", "PROD_MARKERS",
            "DEV_MARKERS")


def main():
    conf, root, fails, warns = _conf.load(), _conf.root(), [], []
    if not (root / "factory.conf").is_file():
        print(f"FAIL  no factory.conf in {root}")
        return 1
    for key in REQUIRED:
        value = conf.get(key, "")
        if not value:
            fails.append(f"{key} is empty")
        elif PLACEHOLDER.search(value):
            fails.append(f"{key} still holds a template placeholder: {value!r}")
    if conf.get("OWNER_NAME") == "Owner":
        fails.append("OWNER_NAME is still 'Owner'")
    prod, dev = _conf.words("PROD_MARKERS", conf), _conf.words("DEV_MARKERS", conf)
    for m in prod + dev:
        # Markers are substrings of the whole command: a short or all-letter word matches inside other words.
        if len(m) < 6 or re.fullmatch(r"[a-z]+", m):
            warns.append(f"marker {m!r} is short or a plain word: it is matched as a substring "
                         "(main matches domain, src/main.py). Use a full profile name, account id or hostname.")
    for m in prod:
        if any(m in d or d in m for d in dev):
            fails.append(f"PROD marker {m!r} and a DEV marker contain each other: every dev command would read as production")
    for repo in _conf.repos(conf):
        if not repo.is_dir():
            warns.append(f"CLIENT_REPOS entry not cloned: {repo}")
    argv = shlex.split(conf.get("MAIL_CLI", ""))
    prog = next((a for a in argv if a != "env" and "=" not in a), "")
    if not prog:
        fails.append("MAIL_CLI names no program")
    elif "=" in argv[0]:
        fails.append("MAIL_CLI starts with VAR=value: write it as \"env VAR=value <program>\"")
    elif not (shutil.which(prog) or os.path.exists(prog)):
        warns.append(f"MAIL_CLI program {prog!r} is not on PATH: drafts and the inbox sweep cannot run on this machine")
    rule = root / ".claude" / "rules" / "client-repos.md"
    if rule.is_file() and "acme" in rule.read_text(encoding="utf-8", errors="replace"):
        warns.append(".claude/rules/client-repos.md still has the acme paths: set them to CLIENT_REPOS")
    for line in fails:
        print("FAIL  " + line)
    for line in warns:
        print("WARN  " + line)
    print(f"check-conf: {len(fails)} fail, {len(warns)} warn  "
          f"(prod markers: {' '.join(prod) or '-'} | dev markers: {' '.join(dev) or '-'} | "
          f"contacts: {conf.get('CLIENT_CONTACT_EMAILS') or '-'})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
