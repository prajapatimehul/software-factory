#!/usr/bin/env python3
"""List client mail of the last N days whose message id is not in ledger/mail.tsv, with its age. Read-only.

  inbox-sweep.py [--days 10] [--record]     --record appends a row for each new one (set its task column afterwards)

"Client mail" = from or to an entry of CLIENT_CONTACT_EMAILS. When MAIL_CLI is missing or not logged in, it says so
and exits 0: a sweep that could not run is reported as not run, never as "nothing new"."""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import MailUnavailable, addresses, append_tsv, conf_list, mail, my_address, read_tsv  # noqa: E402


def main():
    record = "--record" in sys.argv
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 10
    contacts = conf_list("CLIENT_CONTACT_EMAILS")
    if not contacts:
        print("inbox sweep: NOT RUN — CLIENT_CONTACT_EMAILS is empty in factory.conf")
        return
    known = {r["msgid"] for r in read_tsv("ledger/mail.tsv")}
    terms = " OR ".join(f"from:{c.lstrip('@')} OR to:{c.lstrip('@')}" for c in contacts)
    try:
        d = mail("gmail", "users", "messages", "list", "--params",
                 json.dumps({"userId": "me", "q": f"({terms}) newer_than:{days}d", "maxResults": 100}))
        me = my_address()
        new = [m for m in d.get("messages", []) if m["id"] not in known]
        if not new:
            print(f"inbox sweep: nothing unrecorded in {days}d")
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        lines = []
        for m in new:
            g = mail("gmail", "users", "messages", "get", "--params",
                     json.dumps({"userId": "me", "id": m["id"], "format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]}))
            if "DRAFT" in g.get("labelIds", []):
                continue  # a draft has a message id too; draft.py already wrote its draft:<id> row
            h = {x["name"].lower(): x["value"] for x in g.get("payload", {}).get("headers", [])}
            ts = datetime.datetime.fromtimestamp(int(g["internalDate"]) / 1000, datetime.timezone.utc)
            age = now - ts
            fr = (addresses(h.get("from", "")) or [h.get("from", "")])[0].lower()
            direction = "out" if me and fr == me else "in"
            lines.append(f"  [{direction}] {ts:%Y-%m-%d %H:%M} UTC  age {age.days}d {age.seconds // 3600}h  {fr}  | "
                         f"{h.get('subject', '')[:70]}  msgid {m['id']} thread {g['threadId']}")
            if record:
                append_tsv("ledger/mail.tsv", {"date_utc": f"{ts:%Y-%m-%d %H:%M}", "msgid": m["id"], "thread": g["threadId"],
                                               "dir": direction, "from": fr, "to": h.get("to", "")[:60],
                                               "subject": h.get("subject", "")[:70], "note": "swept"})
    except MailUnavailable as e:
        print(f"inbox sweep: NOT RUN — {e}. Unrecorded client mail is unknown, not zero.")
        return
    if not lines:
        print(f"inbox sweep: nothing unrecorded in {days}d")
        return
    print(f"inbox sweep: {len(lines)} unrecorded message(s) in {days}d")
    print("\n".join(lines))
    print("  (recorded in ledger/mail.tsv; set the task column)" if record else "  (add --record to write them to ledger/mail.tsv)")


if __name__ == "__main__":
    main()
