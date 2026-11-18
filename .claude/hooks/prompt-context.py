#!/usr/bin/env python3
"""UserPromptSubmit: when the prompt looks like a pasted client mail, add the matching ledger rows, the open asks
and the open tasks as context, so the reply starts from what was already said and asked. Never blocks."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import CONF, ROOT, _conf, context, file_text, read_payload

try:
    prompt = (read_payload() or {}).get("prompt", "") or ""
    # A background-task notification can carry mail-like lines and is not pasted mail.
    if "<task-notification" in prompt or "[SYSTEM NOTIFICATION" in prompt:
        sys.exit(0)
    contacts = [c.lower() for c in _conf.words("CLIENT_CONTACT_EMAILS", CONF)]
    looks_like_mail = re.search(r"^(from|sent|subject|to):|wrote:\s*$", prompt, re.I | re.M) \
        or any(c in prompt.lower() for c in contacts)
    if not looks_like_mail:
        sys.exit(0)
    from _lib import read_tsv
    ctx = []
    m = re.search(r"^subject:\s*(?:(?:re|fw|fwd):\s*)*(.{4,60})$", prompt, re.I | re.M)
    if m:
        subj = m.group(1).strip()[:30].lower()
        hits = [r for r in read_tsv("ledger/mail.tsv") if subj in (r.get("subject") or "").lower()][-5:]
        if hits:
            ctx.append("ledger/mail.tsv rows on this subject: " + "; ".join(
                f"{r.get('date_utc')} {r.get('dir')} {r.get('from')} msgid {r.get('msgid')} task {r.get('task') or '-'}" for r in hits))
    asks = [r for r in read_tsv("ledger/asks.tsv") if r.get("status") in ("open", "do-not-chase")]
    if asks:
        ctx.append("open asks (never re-send): " + "; ".join(
            f"{r.get('ask_id')} [{r.get('status')}] to {r.get('to')}: {(r.get('wording') or '')[:70]}" for r in asks))
    tasks = [l.split("|") for l in file_text(os.path.join(ROOT, "tasks", "TASKS.md")).splitlines()
             if re.match(r"\|\s*T-\d+\s*\|\s*(open|researching|blocked|waiting-on-client)\s*\|", l)]
    if tasks:
        ctx.append("open tasks: " + "; ".join(f"{t[1].strip()}: {t[3].strip()[:50]}" for t in tasks))
    ctx.append("Before replying: read the whole mail and its attachments, research first, then draft with "
               "scripts/draft.py. Draft only; the owner sends.")
    context("UserPromptSubmit", "\n".join(ctx))
except SystemExit:
    raise
except Exception:
    pass
sys.exit(0)
