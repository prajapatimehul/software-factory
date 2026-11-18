#!/usr/bin/env python3
"""SessionStart (startup|resume|clear|compact): print the digest a session starts from. STATE.md health (size, age,
stamps older than 7 days), the git status of each client repo, open asks, open tasks, live consents, and how many
gate warnings are waiting. Reads only; no network: nothing is fetched and the mailbox is not read (the inbox sweep
is scripts/inbox-sweep.py, run by /task). The full state check is scripts/check-state.sh, run by /checkpoint.
Never fails."""
import datetime
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import CONF, EVID, ROOT, STATE, _conf, file_text, read_tsv


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def state_lines():
    path = os.path.join(ROOT, "STATE.md")
    if not os.path.exists(path):
        return ["STATE.md is missing: nothing describes 'now'. Write it before anything else."]
    out, n, limit = [], file_text(path).count("\n"), _conf.number("STATE_MAX_LINES", CONF)
    if n > limit:
        out.append(f"STATE.md has {n} lines (limit {limit}): move history to STATE-LOG.md.")
    age = int((time.time() - os.path.getmtime(path)) / 86400)
    if age > 7:
        out.append(f"STATE.md was last written {age} days ago: check each line before repeating it.")
    today, stale = datetime.datetime.now(datetime.timezone.utc).date(), 0
    for m in re.finditer(r"\[(?:verified|recorded) (\d{4}-\d{2}-\d{2})", file_text(path)):
        try:
            stale += (today - datetime.date.fromisoformat(m.group(1))).days > 7
        except ValueError:
            pass
    if stale:
        out.append(f"STATE.md has {stale} stamp(s) older than 7 days: re-verify those lines before repeating them "
                   "(bash scripts/check-state.sh lists them).")
    return out or [f"STATE.md: {n} lines, written {age} day(s) ago, no stamp older than 7 days."]


def main():
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"=== {CONF.get('CLIENT_NAME') or '(no client)'} factory: session start {now}, root {ROOT}")
    if not CONF.get("CLIENT_NAME") or not CONF.get("CLIENT_SLUG"):
        print("factory.conf has no CLIENT_NAME / CLIENT_SLUG yet: follow NEW-CLIENT.md.")
    if not _conf.words("PROD_MARKERS", CONF):
        print("factory.conf has no PROD_MARKERS: prod-guard cannot recognise production. Set them.")
    print("--- state")
    for line in state_lines():
        print("  " + line)
    print("--- client repos (local status, not fetched)")
    for repo in _conf.repos(CONF):
        if not os.path.isdir(repo):
            print(f"  {repo.name}: not cloned at {repo}")
            continue
        status = git(repo, "status", "-sb").splitlines()
        print(f"  {repo.name}: {status[0][3:] if status else 'not a git repo'}" + (f", {len(status) - 1} changed file(s)" if len(status) > 1 else ""))
    asks = [r for r in read_tsv("ledger/asks.tsv") if r.get("status") in ("open", "do-not-chase")]
    print(f"--- open asks: {len(asks)} (an ask is sent once; never re-send)")
    for r in asks[:8]:
        print(f"  {r.get('ask_id')} [{r.get('status')}] to {r.get('to')} {r.get('date_utc')}: {(r.get('wording') or '')[:80]}")
    tasks = [l for l in file_text(os.path.join(ROOT, "tasks", "TASKS.md")).splitlines()
             if re.match(r"\|\s*T-\d+\s*\|", l) and not re.match(r"\|[^|]*\|\s*done\s*\|", l)]
    print(f"--- open tasks: {len(tasks)}")
    for l in tasks[:8]:
        c = [x.strip() for x in l.split("|")]
        print(f"  {c[1]} [{c[2]}] {c[3][:70]}")
    try:
        import _consent
        for tok in _consent.TOKENS:
            rec = _consent.live(tok)
            if rec:
                print(f"--- consent live: {tok} until {rec['expires']}")
    except Exception:
        pass
    warnings = file_text(os.path.join(STATE, "gate-warnings.log")).count("\n")
    if warnings:
        print(f"--- gate warnings logged: {warnings} in {os.path.join(STATE, 'gate-warnings.log')} "
              "(what the warn-mode gates would have refused; read them before moving a gate to deny)")
    # Evidence logs hold tool output; two weeks is enough for any open session.
    for name in os.listdir(EVID) if os.path.isdir(EVID) else []:
        path = os.path.join(EVID, name)
        if time.time() - os.path.getmtime(path) > 14 * 86400:
            os.remove(path)
    print("=== rules: drafts only · research before any question · one ask once · claims carry their command · "
          "numbers from tool output · STATE.md wins")


try:
    main()
except Exception as exc:
    print(f"session-start: {exc!r}")
sys.exit(0)
