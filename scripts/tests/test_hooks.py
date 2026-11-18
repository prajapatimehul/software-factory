"""Runs each hook as a subprocess, the way Claude Code does: hook JSON on stdin, a temp FACTORY_ROOT and state
directory, then asserts block or allow.

    python3 -m unittest discover scripts/tests
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / ".claude" / "hooks"
TODAY = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

CONF = """\
CLIENT_NAME="Acme Ltd"
CLIENT_SLUG=acme
OWNER_NAME="Robin"
CLIENT_REPOS="../acme-app"
CLIENT_CONTACT_EMAILS="contact@acme.example"
MAIL_CLI=gws
PROD_MARKERS="acme-prod 000000000000"   # profile name, account id
DEV_MARKERS="acme-dev"
PROD_CONSENT_TOKEN=PROD-WRITE-OK
SEND_CONSENT_PHRASES="send it|ok send"
CONSENT_TTL_MIN=15
MAX_REVIEW_ROUNDS=3
STATE_MAX_LINES=150
"""
GATES = "number-gate=deny\nclaim-gate=deny\nsubagent-stop=deny\nenv-explicit=deny\nread-gate=deny\n"
TRIGGERS = ("id\tapplies\tregex\taction\tentries\trule\n"
            "git-add-all\tbash\tgit add (?:-A|--all|\\.)(?:\\s|$)\tdeny-once\t\tgit add by path.\n"
            "stderr-hidden\tbash\t2>/dev/null[^|]*\\|\\s*wc -l\tnote\t\tstderr is hidden here.\n")


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factory-test-")).resolve()
        self.root = self.tmp / "ops"
        self.client = self.tmp / "acme-app"
        self.state = self.tmp / "state"
        self.home = self.tmp / "home"
        for d in (self.root / "tasks", self.root / "ledger", self.root / "learning", self.root / ".claude",
                  self.client, self.home / ".aws"):
            d.mkdir(parents=True)
        self.write("factory.conf", CONF)
        self.write(".claude/gates.conf", GATES)
        self.write("STATE.md", "# State\n\n## Now\n- **Next:** ship the export\n")
        self.write("RULES.md", "# Rules\nP1 claims carry their command.\n")
        self.write("learning/triggers.tsv", TRIGGERS)
        self.write("ledger/mail.tsv", "date_utc\tmsgid\tthread\tdir\tfrom\tto\tsubject\tattachments\ttask\tasks\tnote\n")
        self.write("ledger/asks.tsv", "ask_id\ttask\tthread\tfirst_msgid\tdate_utc\tto\twording\tstatus\tanswered_by\tchase_after\tnote\n"
                                      "A-001\tT-001\tth1\tm1\t2000-01-01\tclient\tWhich export format do you want\topen\t\t\t\n")
        self.write("tasks/TASKS.md", "| id | status | title | source | due | file |\n|---|---|---|---|---|---|\n"
                                     "| T-001 | open | Export job | mail | | T-001-export.md |\n")
        self.env = {**os.environ, "FACTORY_ROOT": str(self.root), "FACTORY_STATE_DIR": str(self.state), "HOME": str(self.home)}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- helpers ---
    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def run_hook(self, hook, payload=None, raw=None, **extra):
        payload = dict({"session_id": "s1", "cwd": str(self.root)}, **(payload or {}), **extra)
        r = subprocess.run([sys.executable, str(HOOKS / f"{hook}.py")], input=raw if raw is not None else json.dumps(payload),
                           capture_output=True, text=True, env=self.env, timeout=60)
        return r

    def pre(self, hook, tool, **tool_input):
        return self.run_hook(hook, {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input})

    def post(self, hook, tool, response, **tool_input):
        return self.run_hook(hook, {"hook_event_name": "PostToolUse", "tool_name": tool, "tool_input": tool_input,
                                    "tool_response": response})

    def prompt(self, hook, text):
        return self.run_hook(hook, {"hook_event_name": "UserPromptSubmit", "prompt": text})

    @staticmethod
    def out(r):
        try:
            return json.loads(r.stdout)
        except ValueError:
            return {}

    def assertBlocked(self, r, msg=""):
        o = self.out(r)
        blocked = (r.returncode == 2 or o.get("decision") == "block"
                   or o.get("hookSpecificOutput", {}).get("permissionDecision") == "deny")
        self.assertTrue(blocked, f"expected a block {msg}: rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    def assertAllowed(self, r, msg=""):
        o = self.out(r)
        self.assertEqual(r.returncode, 0, f"{msg}: {r.stderr}")
        self.assertNotEqual(o.get("decision"), "block", msg)
        self.assertNotEqual(o.get("hookSpecificOutput", {}).get("permissionDecision"), "deny", f"{msg}: {r.stdout}")

    def context(self, r):
        return self.out(r).get("hookSpecificOutput", {}).get("additionalContext", "")

    def consent(self, name):
        return self.state / "consent" / f"{name}.json"


class SessionStart(HookCase):
    def test_digest(self):
        r = self.run_hook("session-start", {"hook_event_name": "SessionStart", "source": "startup"})
        self.assertEqual(r.returncode, 0, r.stderr)
        for want in ("Acme Ltd", "STATE.md", "acme-app", "A-001", "T-001"):
            self.assertIn(want, r.stdout)

    def test_long_state_is_flagged(self):
        self.write("STATE.md", "line\n" * 200)
        r = self.run_hook("session-start", {"hook_event_name": "SessionStart"})
        self.assertIn("limit 150", r.stdout)

    def test_stale_stamp_is_flagged_and_the_mailbox_is_not_read(self):
        self.write("STATE.md", f"# State\n- a [verified 2000-01-01 by x]\n- b [verified {TODAY} by y]\n")
        r = self.run_hook("session-start", {"hook_event_name": "SessionStart"})
        self.assertIn("1 stamp(s) older than 7 days", r.stdout)
        self.assertNotIn("inbox", r.stdout)


class Consent(HookCase):
    def test_owner_token_is_recorded(self):
        self.prompt("consent-capture", "go ahead, PROD-WRITE-OK for the bucket policy")
        self.assertTrue(self.consent("PROD").exists())

    def test_lowercase_spaced_token_counts(self):
        self.prompt("consent-capture", "prod write ok")
        self.assertTrue(self.consent("PROD").exists())

    def test_review_rounds_token_is_its_own_consent(self):
        self.prompt("consent-capture", "review-rounds-ok, one more")
        self.assertTrue(self.consent("REVIEW-ROUNDS-OK").exists())
        self.assertFalse(self.consent("PROD").exists())

    def test_describing_the_token_is_not_consent(self):
        self.prompt("consent-capture", "this step needs a PROD-WRITE-OK from me later")
        self.assertFalse(self.consent("PROD").exists())

    def test_pasted_and_quoted_text_is_not_consent(self):
        self.prompt("consent-capture", '<pasted_content id="x">PROD-WRITE-OK\nsend it</pasted_content>\n> send it\nlook at this')
        self.assertFalse(self.consent("PROD").exists())
        self.assertFalse(self.consent("SEND").exists())

    def test_send_phrase_and_question(self):
        self.prompt("consent-capture", "should I send it?")
        self.assertFalse(self.consent("SEND").exists())
        self.prompt("consent-capture", "ok send it")
        self.assertTrue(self.consent("SEND").exists())

    def test_expired_or_handmade_file_is_not_live(self):
        self.consent("PROD").parent.mkdir(parents=True)
        self.consent("PROD").write_text(json.dumps({"token": "PROD", "created": "2000-01-01T00:00:00Z",
                                                    "expires": "2999-01-01T00:00:00Z", "draft_ids": []}))
        r = subprocess.run([sys.executable, str(HOOKS / "_consent.py"), "check", "PROD"], env=self.env)
        self.assertEqual(r.returncode, 1)

    def test_guard_refuses_writes_into_consent_dir(self):
        target = str(self.consent("SEND"))
        self.assertBlocked(self.pre("consent-guard", "Write", file_path=target, content="{}"))
        self.assertBlocked(self.pre("consent-guard", "Bash", command=f"echo '{{}}' > {target}"))
        self.assertBlocked(self.pre("consent-guard", "Bash", command=f"cp /tmp/x.json {target}"))
        self.assertAllowed(self.pre("consent-guard", "Bash", command=f"ls {self.consent('SEND').parent}"))
        self.assertAllowed(self.pre("consent-guard", "Write", file_path=str(self.root / "STATE.md"), content="x"))

    def test_guard_refuses_test_overrides_in_a_command(self):
        self.assertBlocked(self.pre("consent-guard", "Bash", command="FACTORY_STATE_DIR=/tmp/fake python3 scripts/send.py --draft-id d1"))
        self.assertAllowed(self.pre("consent-guard", "Bash", command="python3 -m unittest discover scripts/tests"))

    def test_send_needs_live_consent(self):
        cmd = "python3 scripts/send.py --draft-id r-1234567"
        self.assertBlocked(self.pre("consent-guard", "Bash", command=cmd))
        self.assertAllowed(self.pre("consent-guard", "Bash", command="python3 scripts/send.py --help"))
        self.assertAllowed(self.pre("consent-guard", "Bash", command="git commit -m 'fix scripts/send.py'"))
        self.prompt("consent-capture", "send it")
        self.assertAllowed(self.pre("consent-guard", "Bash", command=cmd))

    def test_send_consent_is_bound_to_the_named_draft(self):
        self.prompt("consent-capture", "/send r-1234567")
        self.assertAllowed(self.pre("consent-guard", "Bash", command="python3 scripts/send.py --draft-id r-1234567"))
        self.assertBlocked(self.pre("consent-guard", "Bash", command="python3 scripts/send.py --draft-id r-7654321"))

    def test_guard_fails_closed_on_garbage(self):
        self.assertBlocked(self.run_hook("consent-guard", raw="not json"))


class ProdGuard(HookCase):
    WRITE = "AWS_PROFILE=acme-prod aws s3 rm s3://bucket/key"

    def test_prod_write_needs_consent(self):
        self.assertBlocked(self.pre("prod-guard", "Bash", command=self.WRITE))

    def test_token_typed_by_the_agent_is_not_consent(self):
        self.assertBlocked(self.pre("prod-guard", "Bash", command=self.WRITE + " # PROD-WRITE-OK"))

    def test_owner_consent_plus_token_passes(self):
        self.prompt("consent-capture", "PROD-WRITE-OK")
        self.assertBlocked(self.pre("prod-guard", "Bash", command=self.WRITE), "token missing from the command")
        self.assertAllowed(self.pre("prod-guard", "Bash", command=self.WRITE + " # PROD-WRITE-OK"))

    def test_reads_and_dry_runs_pass(self):
        for cmd in ("AWS_PROFILE=acme-prod aws s3 ls s3://bucket/delete-me/",
                    "AWS_PROFILE=acme-prod aws logs filter-log-events --start-time 1 --log-group-name x",
                    "AWS_PROFILE=acme-prod aws s3 rm s3://bucket/key --dryrun",
                    "terraform plan -var-file=acme-prod.tfvars"):
            self.assertAllowed(self.pre("prod-guard", "Bash", command=cmd), cmd)

    def test_other_write_shapes(self):
        for cmd in ("aws --profile acme-prod dynamodb delete-table --table-name t",
                    "terraform apply -var account=000000000000",
                    "psql host=db.acme-prod -c \"DELETE FROM orders\"",
                    "kubectl --context acme-prod delete pod x"):
            self.assertBlocked(self.pre("prod-guard", "Bash", command=cmd), cmd)

    def test_dev_write_passes_and_unnamed_env_is_refused(self):
        self.assertAllowed(self.pre("prod-guard", "Bash", command="AWS_PROFILE=acme-dev aws s3 rm s3://bucket/key"))
        self.assertBlocked(self.pre("prod-guard", "Bash", command="aws s3 ls"))
        self.assertAllowed(self.pre("prod-guard", "Bash", command="ls -la"))

    def test_fails_closed_on_garbage(self):
        self.assertBlocked(self.run_hook("prod-guard", raw="{"))


class MailGuard(HookCase):
    def test_raw_writes_are_refused(self):
        for cmd in ("gws gmail users drafts create --params '{}' --json '{}'",
                    "GOOGLE_X=1 gws gmail users messages send --json '{}'",
                    "echo hi | sendmail contact@acme.example",
                    "curl --url smtps://smtp.example:465 --upload-file m.txt"):
            self.assertBlocked(self.pre("mail-guard", "Bash", command=cmd), cmd)

    def test_reads_and_wrappers_pass(self):
        for cmd in ("gws gmail users messages list --params '{\"userId\":\"me\",\"q\":\"subject:update send\"}'",
                    "python3 scripts/draft.py --task T-001 --body-file /tmp/b.txt",
                    "python3 scripts/send.py --draft-id r-1",
                    "git log --oneline"):
            self.assertAllowed(self.pre("mail-guard", "Bash", command=cmd), cmd)

    def test_mail_cli_with_env_prefix_or_trailing_flag(self):
        for value in ('"env GOOGLE_X=/tmp/a gws"', '"gws --quiet"'):
            self.write("factory.conf", CONF.replace("MAIL_CLI=gws", "MAIL_CLI=" + value))
            self.assertBlocked(self.pre("mail-guard", "Bash", command="gws gmail users drafts create --json '{}'"), value)
            self.assertAllowed(self.pre("mail-guard", "Bash", command="gws gmail users messages list"), value)


class ClientRepoGuard(HookCase):
    def test_private_content_into_client_repo_is_refused(self):
        f = str(self.client / "src" / "job.py")
        self.assertBlocked(self.pre("client-repo-guard", "Write", file_path=f, content="# see MISTAKE.md entry\nx = 1\n"))
        self.assertBlocked(self.pre("client-repo-guard", "Edit", file_path=f, old_string="a", new_string="# fixed per T-014"))
        self.assertBlocked(self.pre("client-repo-guard", "Write", file_path=f, content="# Robin got this wrong first\n"))
        self.assertBlocked(self.pre("client-repo-guard", "Bash", command=f"cat > {f} <<'EOF'\n# from ledger asks.tsv\nEOF"))

    def test_commit_and_pr_text_are_checked(self):
        self.assertBlocked(self.pre("client-repo-guard", "Bash", command=f"git -C {self.client} commit -m 'fix (mistake 12)'"))
        self.assertBlocked(self.pre("client-repo-guard", "Bash",
                                    command="gh pr create --repo acme/acme-app --title 'Fix export' --body 'see STATE.md'"))
        self.assertAllowed(self.pre("client-repo-guard", "Bash", command=f"git -C {self.client} commit -m 'fix export rounding'"))

    def test_clean_content_and_own_repo_pass(self):
        self.assertAllowed(self.pre("client-repo-guard", "Write", file_path=str(self.client / "a.py"), content="x = 1  # rounding fix\n"))
        self.assertAllowed(self.pre("client-repo-guard", "Write", file_path=str(self.root / "tasks" / "T-001.md"), content="see MISTAKE.md\n"))

    def test_worktree_of_a_client_repo_counts(self):
        wt = self.tmp / "scratch-wt"
        wt.mkdir()
        (self.client / ".git" / "worktrees" / "wt").mkdir(parents=True)
        (wt / ".git").write_text(f"gitdir: {self.client}/.git/worktrees/wt\n")
        self.assertBlocked(self.pre("client-repo-guard", "Write", file_path=str(wt / "a.py"), content="# RULES.md says so\n"))

    def test_fails_closed_on_garbage(self):
        self.assertBlocked(self.run_hook("client-repo-guard", raw=""))


class ClaimAndNumberGates(HookCase):
    def test_claim_needs_its_command(self):
        f = str(self.root / "STATE.md")
        self.assertBlocked(self.pre("claim-gate", "Write", file_path=f, content="- The nightly job is fixed.\n"))
        self.assertAllowed(self.pre("claim-gate", "Write", file_path=f,
                                    content="- The nightly job is fixed.\n  cmd: `make test` → 12 passed\n"))
        self.assertAllowed(self.pre("claim-gate", "Write", file_path=f, content="- Nightly job: not checked yet.\n"))
        self.assertAllowed(self.pre("claim-gate", "Write", file_path=str(self.root / "notes.txt"), content="all done\n"))

    def test_claim_gate_warn_mode_logs_and_passes(self):
        self.write(".claude/gates.conf", "claim-gate=warn\n")
        self.assertAllowed(self.pre("claim-gate", "Write", file_path=str(self.root / "STATE.md"), content="- It is fixed.\n"))
        self.assertIn("claim-gate", (self.state / "gate-warnings.log").read_text())

    def test_number_must_come_from_evidence(self):
        f = str(self.root / "tasks" / "T-001-export.md")
        self.assertBlocked(self.pre("number-gate", "Write", file_path=f, content="Rows exported: 4821\n"))
        self.post("evidence-log", "Bash", {"stdout": "count\n4821\n", "stderr": ""}, command="wc -l out.csv")
        self.assertAllowed(self.pre("number-gate", "Write", file_path=f, content="Rows exported: 4821\n"))
        self.assertAllowed(self.pre("number-gate", "Write", file_path=f, content="See T-001, step 12, on 2026-01-05.\n"))

    def test_number_typed_by_the_owner_counts(self):
        self.prompt("evidence-log", "the budget is 7500 for this month")
        f = str(self.root / "STATE.md")
        self.assertAllowed(self.pre("number-gate", "Write", file_path=f, content="Budget: 7500\n"))


class PostHooks(HookCase):
    def test_empty_result_gets_a_reminder(self):
        r = self.post("empty-result", "Bash", {"stdout": "", "stderr": ""}, command="grep -r token src/ 2>/dev/null")
        self.assertIn("must-match control", self.context(r))
        self.assertIn("2>/dev/null", self.context(r))
        self.assertEqual(self.context(self.post("empty-result", "Bash", {"stdout": "a.py:1:x", "stderr": ""}, command="grep -r x src/")), "")
        self.assertEqual(self.context(self.post("empty-result", "Bash", {"stdout": "", "stderr": ""}, command="mkdir -p out")), "")

    def test_trigger_denies_once_then_passes(self):
        self.assertBlocked(self.pre("trigger-gate", "Bash", command="git add -A"))
        self.assertAllowed(self.pre("trigger-gate", "Bash", command="git add -A"))
        self.assertAllowed(self.pre("trigger-gate", "Bash", command="git add STATE.md"))

    def test_trigger_note_after_the_call(self):
        r = self.post("trigger-gate", "Bash", {"stdout": "0"}, command="ls x 2>/dev/null | wc -l")
        self.assertIn("stderr is hidden", self.context(r))

    def test_evidence_log_records_output(self):
        self.post("evidence-log", "Bash", {"stdout": "id 9f8e7d6c5b4a"}, command="echo")
        self.assertIn("9f8e7d6c5b4a", (self.state / "evidence" / "s1.tokens").read_text())
        self.assertIn("evidence-record", (self.state / "evidence" / "s1.log").read_text())


class ReadGate(HookCase):
    def test_history_is_not_read_whole(self):
        big = self.write("STATE-LOG.md", "old line\n" * 500)
        self.assertBlocked(self.pre("read-gate", "Read", file_path=str(big)))
        self.assertAllowed(self.pre("read-gate", "Read", file_path=str(big), offset=100, limit=200))
        small = self.write("learning/MISTAKE.md", "# Mistakes\n")
        self.assertAllowed(self.pre("read-gate", "Read", file_path=str(small)))
        self.assertAllowed(self.pre("read-gate", "Read", file_path=str(self.root / "STATE.md")))


class CredScan(HookCase):
    def test_printing_a_credentials_file_is_refused(self):
        (self.home / ".aws" / "credentials").write_text("[default]\n")
        self.assertBlocked(self.pre("cred-scan", "Read", file_path=str(self.root / ".env")))
        self.assertBlocked(self.pre("cred-scan", "Bash", command="cat ~/.aws/credentials"))
        self.assertBlocked(self.pre("cred-scan", "Bash", command="cd ~/.aws && head -3 credentials"))
        self.assertBlocked(self.pre("cred-scan", "Bash", command="grep KEY .env.production"))

    def test_safe_reads_pass(self):
        for cmd in ("cat .env.example", "grep -c KEY .env", "cat .env | sed 's/=.*/=<hidden>/'",
                    "TOKEN=$(cat secrets/api.token) && curl -s https://example.com", "cat README.md"):
            self.assertAllowed(self.pre("cred-scan", "Bash", command=cmd), cmd)

    def test_printed_secret_is_flagged_without_the_value(self):
        r = self.post("cred-scan", "Bash", {"stdout": "user admin\npassword hunter2-very-secret\n"}, command="cat notes.txt")
        self.assertIn("password line", self.context(r))
        self.assertNotIn("hunter2", r.stdout)
        self.assertEqual(self.context(self.post("cred-scan", "Bash", {"stdout": "password: <hidden>\n"}, command="x")), "")

    def test_fails_closed_on_garbage(self):
        self.assertBlocked(self.run_hook("cred-scan", raw="nope"))


class Subagents(HookCase):
    def test_start_gets_rules_and_state(self):
        ctx = self.context(self.run_hook("subagent-start", {"hook_event_name": "SubagentStart", "agent_id": "a1"}))
        for want in ("P1 claims carry their command", "ship the export", "Report contract"):
            self.assertIn(want, ctx)

    def test_stop_sends_a_bad_report_back_once(self):
        payload = {"hook_event_name": "SubagentStop", "agent_id": "a1",
                   "last_assistant_message": "Processed 98765 rows.\nEverything is verified."}
        self.assertBlocked(self.run_hook("subagent-stop", payload))
        self.assertAllowed(self.run_hook("subagent-stop", payload), "second time passes")

    def test_stop_passes_a_supported_report(self):
        transcript = self.tmp / "agent.jsonl"
        transcript.write_text(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "98765 rows"}]}}) + "\n")
        payload = {"hook_event_name": "SubagentStop", "agent_id": "a2", "agent_transcript_path": str(transcript),
                   "last_assistant_message": "Rows: 98765\ncmd: `wc -l out.csv` → 98765\nThe rest is not checked."}
        self.assertAllowed(self.run_hook("subagent-stop", payload))


class StopCheck(HookCase):
    def stop(self, message, **extra):
        return self.run_hook("stop-check", dict({"hook_event_name": "Stop", "last_assistant_message": message}, **extra))

    def test_done_needs_proof(self):
        self.prompt("evidence-log", "fix the export")
        self.post("evidence-log", "Edit", {"ok": True}, file_path="/x/job.py")
        self.assertBlocked(self.stop("The export is fixed."))
        self.assertAllowed(self.stop("The export is fixed."), "blocks once per turn")

    def test_check_after_the_edit_passes(self):
        self.prompt("evidence-log", "fix the export")
        self.post("evidence-log", "Edit", {"ok": True}, file_path="/x/job.py")
        self.post("evidence-log", "Bash", {"stdout": "3 passed"}, command="pytest")
        self.assertAllowed(self.stop("The export is fixed."))

    def test_no_claim_or_no_edit_passes(self):
        self.assertAllowed(self.stop("I changed nothing; here is the plan."))
        self.assertAllowed(self.stop("All done."))

    def test_unrecorded_mail_blocks_once(self):
        old = datetime.datetime.now().timestamp() - 3600
        for f in (self.root / "STATE.md", self.root / "tasks" / "TASKS.md"):
            os.utime(f, (old, old))
        with open(self.root / "ledger" / "mail.tsv", "a") as f:
            f.write(f"{TODAY} 10:00\tdraft:r-1\tth1\tout\tme\tclient\tExport\t\tT-001\t\t\n")
        self.assertBlocked(self.stop("Draft created."))
        self.assertAllowed(self.stop("Draft created."))

    def test_stop_hook_active_never_blocks(self):
        self.prompt("evidence-log", "fix it")
        self.post("evidence-log", "Edit", {"ok": True}, file_path="/x/job.py")
        self.assertAllowed(self.stop("It is fixed.", stop_hook_active=True))


class PrMergeGate(HookCase):
    MERGE = "gh pr merge 12 --repo acme/acme-app --squash"

    def test_merge_without_review_is_refused(self):
        self.assertBlocked(self.pre("pr-merge-gate", "Bash", command=self.MERGE))
        self.assertAllowed(self.pre("pr-merge-gate", "Bash", command="gh pr view 12 --repo acme/acme-app"))

    def test_passing_review_today_allows(self):
        self.write("tasks/T-001-export.md", f"# T-001\n\n## Review — {TODAY} acme/acme-app#12\n- verdict: pass\n\n## Next\n")
        self.assertAllowed(self.pre("pr-merge-gate", "Bash", command=self.MERGE))
        self.assertBlocked(self.pre("pr-merge-gate", "Bash", command="gh pr merge 13 --repo acme/acme-app"))
        self.assertBlocked(self.pre("pr-merge-gate", "Bash", command="gh pr merge 12 --repo acme/acme-data"), "other repo")

    def test_round_lines_and_latest_verdict_wins(self):
        body = f"## Review (PR #12)\n- round 1: {TODAY} verdict: fail — missing test\n"
        self.write("tasks/T-001-export.md", body)
        self.assertBlocked(self.pre("pr-merge-gate", "Bash", command="gh pr merge 12"))
        self.write("tasks/T-001-export.md", body + f"- round 2: {TODAY} verdict: pass\n")
        self.assertAllowed(self.pre("pr-merge-gate", "Bash", command="gh pr merge 12"))

    def test_swarm_format_last_dated_line_decides(self):
        lanes = (f"## Review — {TODAY} acme/acme-app#12 at abc1234 — reviewer 1 (claims)\n- verdict: pass\n\n"
                 f"## Review — {TODAY} acme/acme-app#12 at abc1234 — reviewer 2 (tests) — INCOMPLETE\n- no verdict line\n\n"
                 f"### Swarm verdict — {TODAY} acme/acme-app#12 at abc1234: FAIL — round 1/3\n"
                 f"- {TODAY} verdict: fail — swarm of 2 lane(s) on acme/acme-app#12: FAIL\n")
        self.write("tasks/T-001-export.md", lanes)
        self.assertBlocked(self.pre("pr-merge-gate", "Bash", command=self.MERGE))
        self.write("tasks/T-001-export.md", lanes + f"\n## Review — {TODAY} acme/acme-app#12 at def5678 — reviewer 1 (claims)\n"
                   f"verdict: pass with nits\n### Swarm verdict — {TODAY} acme/acme-app#12: PASS WITH NITS — round 2/3\n"
                   f"- {TODAY} verdict: pass — swarm of 1 lane(s) on acme/acme-app#12: PASS WITH NITS\n")
        self.assertAllowed(self.pre("pr-merge-gate", "Bash", command=self.MERGE))

    def test_old_review_and_template_do_not_count(self):
        self.write("tasks/T-001-export.md", "## Review — 2000-01-01 PR #12\n- verdict: pass\n")
        self.write("tasks/TEMPLATE.md", f"## Review PR #12\n- round 1: {TODAY} verdict: pass\n")
        self.assertBlocked(self.pre("pr-merge-gate", "Bash", command="gh pr merge 12"))

    def test_round_limit_is_named(self):
        self.write("tasks/T-001-export.md", "## Review (PR #12)\n" + "".join(
            f"- round {i}: {TODAY} verdict: fail — still broken\n" for i in (1, 2, 3)))
        r = self.pre("pr-merge-gate", "Bash", command="gh pr merge 12")
        self.assertBlocked(r)
        self.assertIn("MAX_REVIEW_ROUNDS=3", r.stderr)


class PromptContext(HookCase):
    def test_pasted_mail_gets_ledger_context(self):
        ctx = self.context(self.prompt("prompt-context", "From: contact@acme.example\nSubject: Re: Export format\n\nHi, any news?"))
        self.assertIn("A-001", ctx)
        self.assertIn("T-001", ctx)

    def test_ordinary_prompt_gets_nothing(self):
        self.assertEqual(self.prompt("prompt-context", "run the tests").stdout.strip(), "")


class Config(HookCase):
    def test_conf_helper(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import _conf; c = _conf.load();"
                "print(c['CLIENT_NAME'], '|', c['PROD_MARKERS'], '|', _conf.root(), '|', _conf.number('CONSENT_TTL_MIN'))")
        r = subprocess.run([sys.executable, "-c", code, str(HOOKS.parents[1] / "scripts")], capture_output=True, text=True, env=self.env)
        self.assertEqual(r.stdout.strip(), f"Acme Ltd | acme-prod 000000000000 | {self.root} | 15", r.stderr)

    def test_every_registered_hook_exists(self):
        settings = json.loads((HOOKS.parent / "settings.json").read_text())
        for groups in settings["hooks"].values():
            for group in groups:
                for h in group["hooks"]:
                    name = h["command"].rsplit("/", 1)[-1]
                    self.assertTrue((HOOKS / name).is_file(), name)
                    self.assertIn('"$CLAUDE_PROJECT_DIR"', h["command"])


if __name__ == "__main__":
    unittest.main()
