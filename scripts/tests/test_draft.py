import datetime
import json
import os
import subprocess
import sys
import unittest

from _fixture import SCRIPTS, make_root, read, run, write

TODAY = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
HOOKS = os.path.join(os.path.dirname(SCRIPTS), ".claude", "hooks")
# A stand-in for the mail CLI: answers from a canned table and logs every call. Nothing leaves the machine.
FAKE = r'''
import json, os, sys
a = sys.argv[1:]
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "calls.log"), "a").write(" ".join(a[:4]) + "\n")
op = " ".join(a[:4])
if op == "gmail users getProfile --params": print(json.dumps({"emailAddress": "owner@us.example"}))
elif op == "gmail users messages get":
    print(json.dumps({"threadId": "th-1", "payload": {"headers": [
        {"name": "From", "value": "Pat <pat@client.example>"}, {"name": "To", "value": "owner@us.example"},
        {"name": "CC", "value": "Sam <sam@partner.example>"}, {"name": "Subject", "value": "Export job"},
        {"name": "Message-ID", "value": "<orig@client.example>"}]}}))
elif op == "gmail users drafts create": print(json.dumps({"id": "r-7000001", "message": {"threadId": "th-1"}}))
elif op == "gmail users drafts send": print(json.dumps({"id": "msg-9", "threadId": "th-1"}))
elif op == "gmail users drafts delete": print("{}")
else: sys.exit("fake mail cli: unexpected call " + op)
'''
TASK = """# T-001 — export job

status: open

## Research (fill via /brief before any question to the client)
Sources checked: [ok 2] tasks
{outcome}

## Evidence (cmd + output, dated)
{evidence}

## Review (written by the reviewer agent)
{review}
## Next
-
"""


class Draft(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = make_root()
        self.addCleanup(self.tmp.cleanup)
        self.fake = os.path.join(self.tmp.name, "fakemail.py")
        with open(self.fake, "w") as f:
            f.write(FAKE)
        write(self.root, "factory.conf", read(self.root, "factory.conf").replace("no-such-mail-cli", f"{sys.executable} {self.fake}"))
        self.task()

    def task(self, outcome="Outcome: Answered", evidence="-", review=""):
        write(self.root, "tasks/T-001-export.md", TASK.format(outcome=outcome, evidence=evidence, review=review))

    def body(self, text, name="T-001-reply.txt"):
        write(self.root, name, text)
        return os.path.join(self.root, name)

    def draft(self, body, *extra, reply=True):
        target = ("--thread", "th-1", "--reply-to", "m-1") if reply else ("--new-thread", "--subject", "Export job", "--to", "pat@client.example")
        return run(self.root, "draft.py", "--task", "T-001", *target, "--body-file", self.body(body), *extra)

    def calls(self):
        p = os.path.join(self.tmp.name, "calls.log")
        if not os.path.exists(p):
            return ""
        with open(p) as f:
            return f.read()

    def rows(self, rel):
        return read(self.root, rel).strip().split("\n")[1:]

    # --- dry run -----------------------------------------------------------

    def test_dry_run_prints_mime_and_touches_nothing(self):
        r = self.draft("Hi Pat,\n\nI will look at the export on Monday.\n\nOwner", "--dry-run", reply=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("To: pat@client.example", r.stdout)
        self.assertIn("Subject: Export job", r.stdout)
        self.assertIn("Nothing was written and no draft was created", r.stdout)
        for rel in ("ledger/mail.tsv", "ledger/asks.tsv", "ledger/promises.tsv"):
            self.assertEqual(self.rows(rel), [], rel)
        self.assertEqual(self.calls(), "")

    def test_dry_run_reply_reads_headers_but_creates_nothing(self):
        r = self.draft("Hi Pat,\n\nThanks, I have the file.\n\nOwner", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Subject: Re: Export job", r.stdout)
        self.assertIn("In-Reply-To: <orig@client.example>", r.stdout)
        self.assertIn("Cc: sam@partner.example", r.stdout)   # the header came as "CC"
        self.assertNotIn("drafts create", self.calls())
        self.assertEqual(self.rows("ledger/mail.tsv"), [])

    # --- asks --------------------------------------------------------------

    def test_ask_without_finished_research_is_refused(self):
        for outcome in ("Outcome: Answered", "Outcome: Answered | Deferred | Conflicting | Awaiting a specific answer | Search incomplete"):
            self.task(outcome=outcome)
            r = self.draft("Hi Pat,\n\nWhich region holds the archive bucket?\n\nOwner", "--ask", "Which region holds the archive bucket?")
            self.assertEqual(r.returncode, 2, outcome)
            self.assertIn("Awaiting a specific answer", r.stderr)
        self.assertEqual(self.rows("ledger/asks.tsv"), [])

    def test_repeated_ask_is_refused(self):
        self.task(outcome="Outcome: Awaiting a specific answer")
        write(self.root, "ledger/asks.tsv", read(self.root, "ledger/asks.tsv")
              + "A-001\tT-001\tth-9\tmsg-1\t2020-01-01 10:00\tpat@client.example\tWhich region holds the archive bucket?\topen\t\t\tsent\n")
        r = self.draft("Hi Pat,\n\nWhich region is the archive bucket in?\n\nOwner", "--ask", "Which region holds the archive bucket, please?")
        self.assertEqual(r.returncode, 2)
        self.assertIn("already with the client — A-001", r.stderr)
        self.assertNotIn("drafts create", self.calls())

    def test_new_ask_is_drafted_and_recorded(self):
        self.task(outcome="Outcome: Awaiting a specific answer")
        r = self.draft("Hi Pat,\n\nWhich region holds the archive bucket?\n\nOwner", "--ask", "Which region holds the archive bucket?")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DRAFT CREATED r-7000001", r.stdout)
        ask = self.rows("ledger/asks.tsv")[0].split("\t")
        self.assertEqual((ask[0], ask[3], ask[7]), ("A-001", "(draft)", "open"))
        mail = self.rows("ledger/mail.tsv")[0].split("\t")
        self.assertEqual((mail[1], mail[2], mail[3], mail[9]), ("draft:r-7000001", "th-1", "out", "A-001"))
        again = self.draft("Hi Pat,\n\nWhich region holds the archive bucket?\n\nOwner")
        self.assertEqual(again.returncode, 2)   # same content, same thread, within 24 h
        self.assertIn("same content", again.stderr)

    # --- claims ------------------------------------------------------------

    def test_claim_needs_dated_cmd_evidence_then_a_review(self):
        body = "Hi Pat,\n\nThe export job is fixed.\n\nOwner"
        r = self.draft(body)
        self.assertEqual(r.returncode, 2)
        self.assertIn("no 'cmd:' line dated", r.stderr)

        self.task(evidence="- 2020-01-01 cmd: `run export job` → exit 0")   # an old line is not today's proof
        self.assertIn("no 'cmd:' line dated", self.draft(body).stderr)

        self.task(evidence=f"- {TODAY} cmd: `run billing report` → exit 0")   # today's line, about something else
        self.assertIn("no Evidence line dated", self.draft(body).stderr)

        ev = f"- {TODAY} cmd: `run export job` → exit 0, 412 rows"
        self.task(evidence=ev)
        r = self.draft(body)
        self.assertEqual(r.returncode, 2)
        self.assertIn("no '## Review' block", r.stderr)

        self.task(evidence=ev, review=f"\n## Review — {TODAY} 10:00 UTC — scope: some other draft.txt\nverdict: pass\n")
        self.assertEqual(self.draft(body).returncode, 2)   # a review of another body does not count
        self.task(evidence=ev, review=f"\n## Review — {TODAY} 10:00 UTC — scope: T-001-reply.txt\nverdict: findings\n")
        self.assertEqual(self.draft(body).returncode, 2)
        self.assertNotIn("drafts create", self.calls())

        self.task(evidence=ev, review=f"\n## Review — {TODAY} 10:00 UTC — scope: T-001-reply.txt\nverdict: pass\n")
        r = self.draft(body)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("drafts create", self.calls())

    # --- recipients and style ---------------------------------------------

    def test_only_client_addresses(self):
        r = run(self.root, "draft.py", "--task", "T-001", "--new-thread", "--subject", "x", "--to", "someone@elsewhere.example",
                "--body-file", self.body("Hi,\n\nA short note.\n\nOwner"), "--dry-run")
        self.assertEqual(r.returncode, 2)
        self.assertIn("CLIENT_CONTACT_EMAILS", r.stderr)
        ok = run(self.root, "draft.py", "--task", "T-001", "--new-thread", "--subject", "x", "--to", "sam@partner.example",
                 "--body-file", self.body("Hi,\n\nA short note.\n\nOwner"), "--dry-run")
        self.assertEqual(ok.returncode, 0, ok.stderr)   # '@partner.example' is a domain entry

    def test_style_gates(self):
        cases = {"words": "word " * 181,
                 "option menu": "Hi Pat,\n\nOption A is the nightly run, option B is the hourly run.\n\nOwner",
                 "tooling words": "Hi Pat,\n\nI asked ChatGPT about the export.\n\nOwner",
                 "tells the client to do something": "Hi Pat,\n\nRun the migration from your laptop.\n\nOwner"}
        for expect, body in cases.items():
            r = self.draft(body, "--dry-run", reply=False)
            self.assertEqual(r.returncode, 2, expect)
            self.assertIn(expect, r.stderr)

    def test_missing_mail_cli_refuses_without_writing_a_draft_row(self):
        write(self.root, "factory.conf", read(self.root, "factory.conf").replace(f"{sys.executable} {self.fake}", "no-such-mail-cli"))
        r = self.draft("Hi Pat,\n\nThanks, I have the file.\n\nOwner", reply=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("not found", r.stderr)
        self.assertEqual(self.rows("ledger/mail.tsv"), [])

    # --- send --------------------------------------------------------------

    def test_send_is_refused_without_consent(self):
        self.draft("Hi Pat,\n\nThanks, I have the file.\n\nOwner")
        r = run(self.root, "send.py", "--draft-id", "r-7000001")
        self.assertEqual(r.returncode, 2)
        self.assertIn("REFUSED", r.stderr)
        self.assertNotIn("drafts send", self.calls())
        self.assertIn("draft:r-7000001", read(self.root, "ledger/mail.tsv"))

    @unittest.skipUnless(os.path.exists(os.path.join(HOOKS, "_consent.py")), "the consent helper is not in this checkout")
    def test_send_with_live_consent_flips_the_ledger_row(self):
        self.draft("Hi Pat,\n\nI will send the file on Monday.\n\nOwner")
        env = dict(os.environ, FACTORY_ROOT=self.root, FACTORY_STATE_DIR=os.path.join(self.root, "state"))
        code = "import sys; sys.path.insert(0, sys.argv[1]); import _consent; _consent.write('SEND', 'send it', 'test', '', [])"
        subprocess.run([sys.executable, "-c", code, HOOKS], env=env, check=True)
        r = run(self.root, "send.py", "--draft-id", "r-7000001")
        self.assertEqual(r.returncode, 0, r.stderr)
        mail = self.rows("ledger/mail.tsv")[0].split("\t")
        self.assertEqual(mail[1], "msg-9")
        self.assertEqual(self.rows("ledger/promises.tsv")[0].split("\t")[2], "msg-9")
        other = run(self.root, "send.py", "--draft-id", "r-0000000")
        self.assertEqual(other.returncode, 2)   # consent is live, but this id is not one of our drafts
        self.assertIn("not made by draft.py", other.stderr)


if __name__ == "__main__":
    unittest.main()
