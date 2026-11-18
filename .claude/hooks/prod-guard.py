#!/usr/bin/env python3
"""PreToolUse on Bash: a write against production needs the owner's live consent.

A command counts as production when it contains one of PROD_MARKERS (a profile name, an account id, a
hostname). When one of its parts also carries a write verb, the command must contain PROD_CONSENT_TOKEN AND the
owner must have typed that token in their own prompt within CONSENT_TTL_MIN (consent-capture.py). Parts with
--dry-run / --dryrun / --help, and plan / diff commands, pass. Any error in the consent check = no consent.

Second rule (mode `env-explicit` in gates.conf): a cloud CLI command that names neither a PROD nor a DEV marker
is ambiguous: a default profile can be the wrong account, and a wrong account returns an empty result, not an error.

Markers are plain substrings of the whole command, so each one must be distinctive: a full profile name, an account
id, a full hostname. A short word (`main`, `prod`) also matches inside `domain` or `src/main.py`."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import CONF, OWNER, _conf, gate, read_payload

CLOUD = re.compile(r"(?:^|[;&|(\s])(?:aws|gcloud|az|kubectl|helm|terraform|tofu|cdk|pulumi)\s")
# Cloud-CLI subcommands are verb-noun (delete-bucket, put-object); the rest are whole words.
VERBS = re.compile(
    r"\b(?:delete|terminate|put|create|update|modify|start|stop|remove|attach|detach|authorize|revoke|reboot|restore|"
    r"reset|rotate|associate|disassociate|enable|disable|register|deregister|add|set|send|execute|cancel|purge|run|"
    r"tag|untag|batch-write)-[a-z]"
    r"|\b(?:s3 (?:rm|rb|mv|cp|sync)|invoke|publish|deploy|destroy|apply|import|migrate|rollback|uninstall|upgrade|"
    r"scale|patch|replace|drain|cordon|exec|push|delete|"
    r"insert into|delete from|drop (?:table|database|schema|index|view)|truncate|alter table|update \w+ set)\b", re.I)
HARMLESS = re.compile(r"--dry-?run|--help|--version|\b(?:plan|diff)\b")


def stripped(seg):
    """Flag names (--start-time), path-like words (s3://x/delete-me/, restore-v4.json) and key=value or
    key:value words (Name=tag:delete-me) are not verbs."""
    seg = re.sub(r"(^|\s)--?[A-Za-z][\w-]*", r"\1", seg)
    return re.sub(r"[^\s\"']*[/.=:][^\s\"']*", " ", seg)


def main():
    p = read_payload()
    if p is None:
        print("prod-guard: could not parse the tool payload; refusing.", file=sys.stderr)
        sys.exit(2)
    if p.get("tool_name") != "Bash":
        return
    cmd = (p.get("tool_input") or {}).get("command", "") or ""
    prod = [m for m in _conf.words("PROD_MARKERS", CONF) if m in cmd]
    dev = [m for m in _conf.words("DEV_MARKERS", CONF) if m in cmd]
    if prod:
        writes = [s.strip() for s in re.split(r"&&|\|\||;|\n", cmd)
                  if not HARMLESS.search(s) and VERBS.search(stripped(s))]
        if writes:
            token = CONF["PROD_CONSENT_TOKEN"]
            try:
                import _consent
                ok = token in cmd and bool(_consent.live("PROD"))
            except Exception:
                ok = False
            if not ok:
                print(f"prod-guard: this is a WRITE against PRODUCTION (marker {prod[0]!r}): {writes[0][:120]!r}. "
                      f"It needs {token} in the same command, and {token} counts only when {OWNER} typed it in their own "
                      f"prompt in the last {CONF['CONSENT_TTL_MIN']} min. The word typed by the agent or a script does not "
                      f"count. Reads, --dry-run, --help, plan and diff pass. Ask {OWNER}; do not retry.", file=sys.stderr)
                sys.exit(2)
        return
    if CLOUD.search(cmd) and not dev and not HARMLESS.search(cmd) \
            and _conf.words("PROD_MARKERS", CONF) and _conf.words("DEV_MARKERS", CONF):
        gate("env-explicit", p, "prod-guard: say which environment. This cloud command names neither a DEV marker "
             f"({CONF['DEV_MARKERS']}) nor a PROD marker ({CONF['PROD_MARKERS']}); a default profile can be the wrong "
             "account, and a wrong account returns empty, not an error.")


try:
    main()
except SystemExit:
    raise
except Exception as exc:   # fail closed: a broken prod guard must not wave a write through
    print(f"prod-guard: internal error {exc!r}; refusing.", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
