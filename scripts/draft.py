#!/usr/bin/env python3
"""The only way a mail to the client is created. It makes a DRAFT through MAIL_CLI and never sends.

  draft.py --task T-NNN --thread <threadId> --reply-to <msgid> --body-file F [options]     reply on a thread
  draft.py --task T-NNN --new-thread --subject "…" --to <address> --body-file F [options]  start a thread
  draft.py --delete <draft-id>                                                              withdraw one of our drafts

options: --ask "<exact wording>"   the one question this mail carries
         --long                    more than 180 words (needs 'mail-kind: report' in the task file from 200 words)
         --replace <draft-id>      delete that draft once the new one has passed every gate
         --attach F                repeatable
         --no-cc                   do not copy the other recipients of the original
         --dry-run                 run every gate, print the MIME, write nothing and create nothing

It refuses when:
  - the same ask is already open in ledger/asks.tsv
  - --ask is given but the task's Research block does not end 'Outcome: Awaiting a specific answer'
  - the same content went out on the thread in the last 24 h
  - the body has a claim word and the task's Evidence has no '- <today> cmd:' line that covers it
  - the body has a claim, or says how something works, and the task has no '## Review' block of today that names
    this body file and says 'verdict: pass'
  - the body tells the client to do something and the task has no 'mail-kind: ask-ok' + '## Cannot-do proof'
  - the body offers a menu of options, names our tooling, or is too long
  - To is a no-reply address or not in CLIENT_CONTACT_EMAILS
Ledger rows are written first, then the draft, then the draft id is recorded."""
import argparse
import base64
import datetime
import json
import mimetypes
import os
import re
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (BANNED_TO, addresses, append_tsv, conf, die, is_client_address, mail_or_die, my_address, next_id,  # noqa: E402
                     normalise, now_utc, overlap, path, read_tsv, rewrite_tsv, today)

MAX_WORDS = 180
CLAIM_WORDS = (r"\b(works|working now|fixed|tested|done|runs now|is empty|is missing|blocked|cannot|can't|not possible|"
               r"verified|confirmed|deleted|restored|live|deployed)\b")
# A sentence that says HOW something works on the client's or a vendor's side is a claim too, even with no claim word.
MECHANISM_WORDS = r"\b(authoriz\w*|token\w*|the api (gives|returns|allows)|needs? (its|their) own|must|only (the|one)|per (country|account|user|tenant))\b"
TOOLING = r"\b(chatgpt|chat gpt|claude|gpt|copilot|codex|llm|ai agent)\b"
MENU = r"\b(option a|option b|either .* or|your call|which do you prefer)\b"
IMPERATIVE = r"^(run|then run|apply|deploy|execute|merge|pull|click|open|set|change|add|delete|paste)\b"
HEADERS = ("Message-ID", "Subject", "References", "From", "To", "Cc")


def sentences(body):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n", body) if s.strip()]


def delete_draft(victim, dry=False):
    rows = read_tsv("ledger/mail.tsv")
    keep = [r for r in rows if r["msgid"] != f"draft:{victim}"]
    if len(keep) == len(rows):
        die(f"REFUSED: {victim} is not a draft made by draft.py.")
    if dry:
        print(f"dry run: would delete draft {victim} and its ledger row")
        return
    mail_or_die("gmail", "users", "drafts", "delete", "--params", json.dumps({"userId": "me", "id": victim}))
    rewrite_tsv("ledger/mail.tsv", keep)
    print(f"deleted draft {victim}, ledger row removed")


def gate_ask(a, thread, task_text):
    asks = read_tsv("ledger/asks.tsv")
    for r in asks:
        if r["status"] not in ("open", "do-not-chase"):
            continue
        ov = overlap(r["wording"], a.ask)
        if ov > 0.45 or (r["thread"] == thread and ov > 0.25):
            die(f"REFUSED: this ask is already with the client — {r['ask_id']} sent {r['date_utc']} on thread {r['thread']}: "
                f"\"{r['wording']}\" (status {r['status']}, overlap {ov:.2f}). Nothing to send.")
    same = [r["ask_id"] for r in asks if r["status"] == "open" and r["thread"] == thread]
    if same:
        print(f"NOTE: {len(same)} ask(s) already open on this thread ({', '.join(same)}) — one ask per mail; answer their questions first.")
    research = task_text.split("## Research")[1].split("\n## ")[0] if "## Research" in task_text else ""
    # The template line lists all five outcomes separated by '|'; that is an unfinished block, not an outcome.
    if not re.search(r"^Outcome:\s*Awaiting a specific answer\s*$", research, re.M):
        die("REFUSED: --ask given but the task's Research block does not end in 'Outcome: Awaiting a specific answer'. "
            "Run /brief first (research before asking).")


def gate_duplicate(a, thread, body):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    for r in read_tsv("ledger/mail.tsv"):
        # --replace runs after the gates, so the draft being replaced is still in the ledger here.
        if a.replace and r["msgid"] == f"draft:{a.replace}":
            continue
        if r["thread"] != thread or r["dir"] != "out":
            continue
        try:
            ts = datetime.datetime.strptime(r["date_utc"], "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
        note = r.get("note") or ""
        if ts > cutoff and note.startswith("body:") and overlap(note[5:], body[:300]) > 0.8:
            die(f"REFUSED: a mail with the same content is already on this thread from {r['date_utc']} UTC (msgid {r['msgid']}).")


def gate_claims(a, body, task_text):
    # Split on "\n## ", not "## ": a "### " subheading must not cut the Evidence section short.
    ev = task_text.split("## Evidence")[1].split("\n## ")[0] if "## Evidence" in task_text else ""
    ev_today = [l for l in ev.split("\n") if re.search(rf"-\s*{today()}.*cmd:", l)]
    ev_words = set(normalise(" ".join(ev_today)).split())
    claims = False
    for sent in sentences(body):
        if not re.search(CLAIM_WORDS, sent, re.I):
            continue
        claims = True
        if not ev_today:
            die(f"REFUSED: \"{sent.strip()[:80]}\" is a claim but the task's Evidence has no 'cmd:' line dated {today()}. "
                "Run the command that could prove it false, paste it with its output, then draft.")
        nouns = [w for w in normalise(sent).split() if len(w) > 3 and not re.fullmatch(CLAIM_WORDS, w)]
        if nouns and not (set(nouns) & ev_words):
            die(f"REFUSED: \"{sent.strip()[:80]}\" claims something no Evidence line dated {today()} mentions "
                f"(looked for any of: {', '.join(nouns[:6])}). Paste the command and its output into the task file first.")
    mechanism = any(re.search(MECHANISM_WORDS, s, re.I) for s in sentences(body))
    if not (claims or mechanism):
        return
    # The author's own evidence is not enough: the author designs checks that confirm. The review must be of THIS
    # body, so the heading has to name the body file; a same-day review of other claims does not count.
    name = os.path.basename(a.body_file)
    for m in re.finditer(r"(?:^|\n)## Review\b[^\n]*\n", task_text):
        block = task_text[m.end():].split("\n## ")[0]
        if today() in m.group(0) and name in m.group(0) and re.search(r"^\s*[-*]?\s*verdict:\s*pass\b", block, re.M | re.I):
            return
    die(f"REFUSED: the body makes claims or says how something works, but {a.task} has no '## Review' block dated {today()} "
        f"whose heading names this body file ({name}) with 'verdict: pass'. Spawn the work-reviewer agent on THIS body "
        "(read-only: every sentence is proven by a command run today, or removed), paste its block into the task file, "
        "fix what it finds, then draft again.")


def gate_style(a, body, task_text):
    words = len(body.split())
    if words > MAX_WORDS and not a.long:
        die(f"REFUSED: {words} words. The client reads on a phone: at most {MAX_WORDS} unless --long (a report they asked for).")
    # --long is for a report the client asked for, not for a status.
    if a.long and words >= 200 and not re.search(r"^mail-kind:\s*report\s*$", task_text, re.M):
        die(f"REFUSED: {words} words with --long, but {a.task} does not declare 'mail-kind: report'. A status says what is "
            "done, what is next and what they must do. Add the line only if the client asked for a report.")
    for ln in body.split("\n"):
        t = ln.strip()
        # "Nothing to do on your side" is the wording we want, so negations are exempt.
        if not t or re.search(r"\b(nothing|no action|not needed)\b", t, re.I):
            continue
        if re.match(IMPERATIVE, t, re.I) or re.search(r"\b(on|from) your (laptop|machine|console)\b", t, re.I):
            if not re.search(r"^mail-kind:\s*ask-ok\s*$", task_text, re.M) or "## Cannot-do proof" not in task_text:
                die(f"REFUSED: \"{t[:70]}\" tells the client to do something. First prove we cannot do it ourselves: "
                    f"'it is their area' is a claim and needs the command that could prove it false. If it really is "
                    f"theirs, add 'mail-kind: ask-ok' to {a.task} and a '## Cannot-do proof' section listing every "
                    "process of ours that touches the resource and the command that showed it cannot.")
    if re.search(TOOLING, body, re.I):
        die("REFUSED: tooling words in the body. The client hears about the work, not the tools.")
    if re.search(MENU, body, re.I):
        die("REFUSED: option menu. Recommend one thing and invite a veto.")
    return words


def recipients(a, thread):
    """(to, cc list, headers of the original) — read back from the mail tool, never typed."""
    if a.new_thread:
        return a.to, [], {"Subject": a.subject}
    orig = mail_or_die("gmail", "users", "messages", "get", "--params",
                       json.dumps({"userId": "me", "id": a.reply_to, "format": "metadata", "metadataHeaders": list(HEADERS)}))
    # Header names are case-insensitive; some servers send "CC". Map every name onto the spelling used here.
    canon = {n.lower(): n for n in HEADERS}
    h = {canon.get(x["name"].lower(), x["name"]): x["value"] for x in orig.get("payload", {}).get("headers", [])}
    if orig.get("threadId") != thread:
        die(f"REFUSED: msgid {a.reply_to} is on thread {orig.get('threadId')}, not {thread}.")
    me = my_address()
    to = h.get("From", "")
    if me and me in to.lower():
        to = h.get("To", "")
    # A reply keeps everyone who was on the message; otherwise the other recipients are dropped without a word.
    in_to = {x.lower() for x in addresses(to)}
    cc = []
    for x in addresses(h.get("To", "")) + addresses(h.get("Cc", "")):
        xl = x.lower()
        if xl == me or xl in in_to or xl in (o.lower() for o in cc):
            continue
        cc.append(x)
    return to, cc, h


def build(a, body, to, cc, h):
    for f in a.attach:
        if not os.path.exists(f):
            die(f"REFUSED: --attach {f} does not exist.")
    if a.attach:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "plain", "utf-8"))
        total = 0
        for f in a.attach:
            data = open(f, "rb").read()
            total += len(data)
            maintype, subtype = (mimetypes.guess_type(f)[0] or "application/octet-stream").split("/", 1)
            part = MIMEBase(maintype, subtype)
            part.set_payload(data)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=os.path.basename(f))
            msg.attach(part)
        # base64 grows the payload by a third; refuse well before the mail service does.
        if total > 15 * 1024 * 1024:
            die(f"REFUSED: {total / 1048576:.1f} MB of attachments; keep it under 15 MB.")
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to
    if cc and not a.no_cc:
        msg["Cc"] = ", ".join(cc)
    if a.new_thread:
        msg["Subject"] = a.subject
    else:
        subj = h.get("Subject", "")
        msg["Subject"] = subj if subj.lower().startswith("re:") else "Re: " + subj
        msg["In-Reply-To"] = h.get("Message-ID", "")
        msg["References"] = (h.get("References", "") + " " + h.get("Message-ID", "")).strip()
    return msg


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for flag in ("--task", "--thread", "--reply-to", "--body-file", "--ask", "--replace", "--delete", "--subject", "--to"):
        ap.add_argument(flag)
    for flag in ("--new-thread", "--long", "--no-cc", "--dry-run"):
        ap.add_argument(flag, action="store_true")
    ap.add_argument("--attach", action="append", default=[])
    a = ap.parse_args()
    if a.delete:
        return delete_draft(a.delete, a.dry_run)
    if a.new_thread:
        if not (a.task and a.subject and a.to and a.body_file):
            die(__doc__)
        thread = "new"  # the ledger row gets the real thread id from the created draft
    else:
        if not (a.task and a.thread and a.reply_to and a.body_file):
            die(__doc__)
        thread = a.thread
    body = open(a.body_file).read().strip()
    if not body:
        die("REFUSED: the body file is empty.")
    if not re.fullmatch(r"T-\d+", a.task):
        die("REFUSED: --task looks like T-012.")
    tf = sorted(f for f in os.listdir(path("tasks")) if f.startswith(a.task + "-") and f.endswith(".md"))
    if not tf:
        die(f"REFUSED: no task file for {a.task} in tasks/ — create it from tasks/TEMPLATE.md first.")
    task_text = open(path("tasks", tf[0])).read()

    if a.ask:
        gate_ask(a, thread, task_text)
    gate_duplicate(a, thread, body)
    gate_claims(a, body, task_text)
    words = gate_style(a, body, task_text)
    if a.replace and not any(r["msgid"] == f"draft:{a.replace}" for r in read_tsv("ledger/mail.tsv")):
        die(f"REFUSED: --replace {a.replace} is not a draft made by draft.py.")

    to, cc, h = recipients(a, thread)
    to_addrs = addresses(to)
    if not to_addrs:
        die(f"REFUSED: no address in To ({to!r}).")
    if any(b in to.lower() for b in BANNED_TO):
        die(f"REFUSED: To would be {to}.")
    if not all(is_client_address(x) for x in to_addrs):
        die(f"REFUSED: To {to} is not in CLIENT_CONTACT_EMAILS (factory.conf).")
    msg = build(a, body, to, cc, h)
    names = [os.path.basename(f) for f in a.attach]

    if a.dry_run:
        print(msg.as_string())
        print(f"\n--- dry run: every gate passed; {words} words; To {to}; {len(names)} attachment(s); "
              f"ask {'yes' if a.ask else 'none'}. Nothing was written and no draft was created.")
        return

    # --replace runs after the gates: deleting first would leave no draft at all when the new one is refused.
    if a.replace:
        delete_draft(a.replace)
    # Ledger first: a crash after this leaves a row to explain, never an untracked draft.
    ask_id = ""
    if a.ask:
        ask_id = next_id("ledger/asks.tsv", "ask_id", "A")
        append_tsv("ledger/asks.tsv", {"ask_id": ask_id, "task": a.task, "thread": thread, "first_msgid": "(draft)",
                                       "date_utc": now_utc(), "to": to, "wording": a.ask, "status": "open",
                                       "note": "drafted, not sent"})
    for p in re.findall(r"\b(I will [^.\n]{5,80}|I'll [^.\n]{5,80}|We will [^.\n]{5,80}|We'll [^.\n]{5,80})", body):
        append_tsv("ledger/promises.tsv", {"promise_id": next_id("ledger/promises.tsv", "promise_id", "P"), "task": a.task,
                                           "msgid": "(draft)", "date_utc": now_utc(), "to": to, "wording": p.strip(),
                                           "status": "open"})
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    message = {"raw": raw} if a.new_thread else {"raw": raw, "threadId": thread}
    d = mail_or_die("gmail", "users", "drafts", "create", "--params", json.dumps({"userId": "me"}),
                    "--json", json.dumps({"message": message}))
    did = d.get("id", "?")
    if a.new_thread:
        thread = (d.get("message") or {}).get("threadId", "new")
        if ask_id:  # the ask row was written before the thread existed
            asks = read_tsv("ledger/asks.tsv")
            for r in asks:
                if r["ask_id"] == ask_id:
                    r["thread"] = thread
            rewrite_tsv("ledger/asks.tsv", asks)
    append_tsv("ledger/mail.tsv", {"date_utc": now_utc(), "msgid": f"draft:{did}", "thread": thread, "dir": "out",
                                   "from": my_address() or conf("OWNER_NAME"), "to": to[:60], "subject": msg["Subject"][:70],
                                   "attachments": ";".join(names), "task": a.task, "asks": ask_id,
                                   "note": "body:" + body[:300].replace("\n", " ")})
    print(f"DRAFT CREATED {did} on thread {thread} → {to}\n{words} words; {len(names)} attachment(s)"
          f"{': ' + ', '.join(names) if names else ''}; ask {ask_id or 'none'}; ledger rows written.\n"
          f"The owner sends it: /send {did}")


if __name__ == "__main__":
    main()
