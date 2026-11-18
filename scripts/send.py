#!/usr/bin/env python3
"""Sends a draft that draft.py created. Only on the owner's word.

  send.py --draft-id <id>

It needs a live SEND consent: a record written by the consent hook from the owner's own prompt (one of
SEND_CONSENT_PHRASES, or /send <id>), or by `scripts/consent.py from-ask SEND` from an answer the owner picked.
A flag typed by the agent is not consent, so there is no such flag. When the consent names draft ids, this draft must
be one of them. Then it re-checks the thread for the same content sent today, sends, and replaces the ledger row
draft:<id> with the real message id."""
import json
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from _common import (MailUnavailable, conf, consent_module, die, mail, now_utc, overlap, read_tsv, rewrite_tsv,  # noqa: E402
                     today)


def consent_ok(draft_id):
    c = consent_module()
    if c is None or not hasattr(c, "live"):
        return False, "the consent helper (.claude/hooks/_consent.py) is missing, so nothing can prove consent"
    try:
        if c.live("SEND", draft_id):
            return True, ""
    except Exception:
        pass
    owner = conf("OWNER_NAME") or "the owner"
    return False, (f"no live send consent for draft {draft_id}. It counts only when {owner} gave it in the last "
                   f"{conf('CONSENT_TTL_MIN')} min: typed in their own prompt ({conf('SEND_CONSENT_PHRASES')}, or /send <id>) "
                   "or picked in an answer recorded by `python3 scripts/consent.py from-ask SEND`. Ask; do not retry.")


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "--draft-id":
        die(__doc__)
    did = sys.argv[2]
    ok, why = consent_ok(did)
    if not ok:
        die("REFUSED: " + why)
    rows = read_tsv("ledger/mail.tsv")
    row = next((r for r in rows if r["msgid"] == f"draft:{did}"), None)
    if not row:
        die("REFUSED: this draft id is not in ledger/mail.tsv — it was not made by draft.py.")
    for r in rows:
        if (r["thread"] == row["thread"] and r["dir"] == "out" and not r["msgid"].startswith("draft:")
                and r["date_utc"][:10] == today() and (r.get("note") or "").startswith("body:")
                and overlap(r["note"][5:], (row.get("note") or "")[5:]) > 0.8):
            die(f"REFUSED: the same content was already sent today on this thread (msgid {r['msgid']}).")
    try:
        d = mail("gmail", "users", "drafts", "send", "--params", json.dumps({"userId": "me"}), "--json", json.dumps({"id": did}))
    except MailUnavailable as e:
        die(f"REFUSED: {e}")
    mid = d.get("id", "?")
    row["msgid"] = mid
    row["date_utc"] = now_utc()
    if d.get("threadId"):
        row["thread"] = d["threadId"]
    rewrite_tsv("ledger/mail.tsv", rows)
    asks = read_tsv("ledger/asks.tsv")
    ask_ids = set((row.get("asks") or "").replace(",", " ").split())
    for a in asks:
        # A withdrawn "(draft)" row belongs to a draft that was never sent; leave it alone.
        if a["first_msgid"] == "(draft)" and a["ask_id"] in ask_ids and a.get("status") != "withdrawn":
            a["first_msgid"] = mid
            a["note"] = "sent"
    rewrite_tsv("ledger/asks.tsv", asks)
    ps = read_tsv("ledger/promises.tsv")
    for p in ps:
        if p["msgid"] == "(draft)" and p["task"] == row["task"] and p.get("status") != "withdrawn":
            p["msgid"] = mid
    rewrite_tsv("ledger/promises.tsv", ps)
    print(f"SENT msgid {mid} on thread {row['thread']}; ledger updated. Now /checkpoint (task file 'Sent / drafted', STATE.md).")


if __name__ == "__main__":
    main()
