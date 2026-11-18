# The harness: what is enforced and what is only prose

One row per hook. **Expectation** is what a reader would assume. **Mechanism** is the code that makes it true.
**Limit** is where it stops being true. Keep this table honest: when a hook changes, its row changes in the same commit.
A rule with no row here is prose, and prose is followed until the day it is not.

All hooks live in `.claude/hooks/`, are registered in `.claude/settings.json`, read `factory.conf` through
`scripts/_conf.py`, and are tested by `scripts/tests/test_hooks.py`
(`python3 -m unittest discover scripts/tests`).

## Enforced

| Expectation | Mechanism | Limit |
|---|---|---|
| A session starts from the current state, not from memory | `session-start.py` (SessionStart, also after compact): STATE.md size against `STATE_MAX_LINES`, its age and a count of stamps older than 7 days, local git status of each `CLIENT_REPOS` entry, open asks, open tasks, live consents, count of gate warnings | Prints, never blocks. Nothing is fetched, so "up to date" means "as of the last fetch". The mailbox is not read: the inbox sweep is `scripts/inbox-sweep.py`, run by `/task`, and the full state check is `scripts/check-state.sh`, run by `/checkpoint`. It cannot tell whether a line in STATE.md is still true. |
| A write to production needs the owner's yes | `prod-guard.py` (PreToolUse, Bash): a command that contains a `PROD_MARKERS` string and a write verb is refused unless it carries `PROD_CONSENT_TOKEN` **and** a consent file made from the owner's own prompt is live. Parts with `--dry-run` / `--help`, and `plan` / `diff`, pass. Fails closed | The verb list is a regex: an unlisted write verb passes, and some reads are refused (`s3 cp` download, `start-query`). A command that reaches production without naming a marker (a default profile, a script that hard-codes the account) is not seen. A marker is a plain substring of the whole command: a short one (`main`, `prod`) also matches `domain` or `src/main.py` and turns development commands into refused production writes, so list full profile names, account ids and hostnames only. A mention of a marker next to a verb in a commit message, or in an `echo`, is refused too. |
| A cloud command says which environment it means | `prod-guard.py`, second rule: `aws` / `gcloud` / `az` / `kubectl` / `helm` / `terraform` / `cdk` / `pulumi` with neither a PROD nor a DEV marker. Mode `env-explicit` in `gates.conf` | Default mode is `warn`: logged, not refused. Other CLIs (database clients, vendor tools) are not covered. |
| A consent word is the owner's, not the agent's | `consent-capture.py` (UserPromptSubmit) writes `<state dir>/consent/PROD.json`, `SEND.json` or `REVIEW-ROUNDS-OK.json`, live `CONSENT_TTL_MIN` minutes, only from text the owner typed: pasted blocks, task notifications and `> ` quotes are removed, and "needs a PROD-WRITE-OK" or a question is not consent. A send consent that names draft ids covers only those drafts. `_consent.py live()` refuses an expired file and one whose lifetime is longer than the TTL | An answer picked in a question dialog is not a prompt; `scripts/consent.py from-ask` is the only path for it. Consent is per machine, not per session: a token typed in one session is live for another session on the same machine for the TTL. The files sit in the user's home, so a process outside these hooks can write one. |
| Consent files stay human-made | `consent-guard.py` (PreToolUse, Bash and file writes): refuses a Write/Edit into the consent directory or a session transcript, a Bash command that touches the consent directory other than `ls` / `cat` / `rm` / the consent scripts, a command that sets `FACTORY_STATE_DIR` or `FACTORY_ROOT`, and a run of `scripts/send.py` without a live SEND consent for that draft. Fails closed on a bad payload | Pattern-based. A script written to disk and run later, or an interpreter one-liner that builds the path from pieces, is not recognised. `send.py` checks consent again itself; that second check is the real gate. |
| The agent drafts mail and never sends it | `permissions.deny` in `settings.json` (raw `gws gmail` writes and the Gmail connector) + `mail-guard.py` (PreToolUse, Bash): a `MAIL_CLI` write (`drafts create`, `messages send` ...) outside `scripts/draft.py` / `scripts/send.py`, and direct senders (`sendmail`, `msmtp`, `mutt`, `smtp://`), are refused | The deny list is written for `gws`. With another `MAIL_CLI`, edit it. The guard looks for the program word of `MAIL_CLI` (the first word that is not `env` or `VAR=value`). A mail sent by another tool, an HTTP API call, or the owner's phone is outside both. |
| Nothing private reaches a client repo | `client-repo-guard.py` (PreToolUse, file writes and Bash): for a path inside `CLIENT_REPOS` or one of their git worktrees, refuses text that names this repo's files and ids (`MISTAKE.md`, `STATE.md`, ledger files, `T-014`, "mistake 12"), this repo's directory name, `PRIVATE_WORDS` (optional key in `factory.conf`), or the owner next to "said / wrong / forgot". Covers heredocs and redirects, commit / tag / merge messages, and `gh pr|issue|release` titles and bodies. Reads the payload, so it blocks before the bytes land. Fails closed on a bad payload | A fixed word list: private content phrased in other words passes. A file copied with `cp`, or written by a script, is not inspected. A clone that is not listed in `CLIENT_REPOS` and is not a worktree of one is not a client repo to this hook. |
| A claim carries its command where it is written | `claim-gate.py` (PreToolUse, Write/Edit into STATE.md, STATE-LOG.md, `tasks/`, `ledger/claims.tsv`, `docs/`, `decisions/`): a new line with a claim word (done, fixed, live, empty, blocked, all of them ...) needs `cmd:` or `` `command` → output `` within three lines. Headings, Next / Open / TODO lines, questions and "not checked" are exempt. Mode `claim-gate` | Default mode is `warn`. Word-list based: a claim in other words passes, and it checks that a command is written, not that the command proves the claim. |
| Numbers come from tool output | `number-gate.py` (PreToolUse, Write/Edit into the state, task, ledger, learning, docs and decisions files): every time, id, decimal and integer of two or more digits in the new text must be in this session's evidence or already in the file; one derived value passes on a line that says "computed". Mode `number-gate` | Default mode is `warn`. A number seen in an earlier session is unknown to this one. Single digits, dates, years and our own ids are not checked. A right number copied next to the wrong label passes. |
| The gates know what this session saw | `evidence-log.py` (PostToolUse on every tool, UserPromptSubmit): appends tool output and prompts to `<state dir>/evidence/<session>.log` and their tokens to `.tokens` | Output is cut at 300,000 characters per call. The log can hold whatever a tool printed, secrets included; it stays outside the repo and is deleted after 14 days by `session-start.py`. |
| An empty result gets its control before it becomes "absent" | `empty-result.py` (PostToolUse, Bash): a query-like command that printed nothing, an empty list, or a bare 0 gets a reminder to run a must-match control; names stderr hidden by `2>/dev/null` | Adds context only. It cannot check that the control was run. |
| A past mistake is shown when it is about to repeat | `trigger-gate.py` + `learning/triggers.tsv` (`id`, `applies`, `regex`, `action`, `entries`, `rule`): a `deny-once` row refuses a matching Bash / Write / Edit once with the rule and lets the same call through the second time; a `note` row adds the rule after a Bash call. Fired / overridden counts in `<state dir>/trigger-counts.json` | A reminder, not a wall: the unchanged call passes on retry. Only as good as the regexes in the file. |
| History files are not read whole | `read-gate.py` (PreToolUse, Read): `learning/MISTAKE.md`, `learning/LEARNING.md`, `STATE-LOG.md` and `mail/raw/*` longer than 400 lines need `limit` ≤ 400. Mode `read-gate`, `deny` in the shipped `gates.conf` | `cat` through Bash is not covered. |
| A secret does not land in the transcript | `cred-scan.py`. PreToolUse (Bash, Read, Grep): refuses printing `~/.aws/credentials*`, `*.pem` / `*.key` / `*.p12` / `*.token`, ssh private keys, `client_secret*.json`, `token*.json` under `~/.config`, and `.env` files; a masking `sed … <hidden>`, a counting grep and a read inside `$( … )` pass. PostToolUse: output that looks like a secret adds a warning naming the kind, never the value | Known paths and known shapes only. A secret in an unlisted file, or in an unlisted format, passes both halves. A recursive grep over a directory that contains a credentials file is not caught. The PostToolUse half runs after the secret is already in the transcript: it limits the spread, it does not undo it. |
| A subagent starts with the rules and the current state | `subagent-start.py` (SubagentStart): RULES.md, the first section of STATE.md and the report contract as context, under 10,000 characters | Context is not obedience. A long RULES.md is cut at 5,500 characters. |
| A subagent's report is checked against what it saw | `subagent-stop.py` (SubagentStop): every number / id in the final message must be in the agent's own transcript or the session evidence; every claim line needs its command. In `deny` mode a failing report is sent back once per agent. Mode `subagent-stop` | Default mode is `warn`. Sent back once, then it passes whatever it says. |
| A turn does not end on an unrecorded mail, a broken mistake log, or an unproven "done" | `stop-check.py` (Stop): (a) a mail row dated today with neither STATE.md nor a task file touched after it; (b) `scripts/mistakes.py check` red; (c) the turn edited a file and the last message claims done / fixed / works with no Bash / Read / Grep after the last edit. Each blocks once | Each check blocks once and then lets the turn end. (c) accepts any check after the edit, not the right one. Tests are not run by this hook. |
| A merge needs a passing review | `pr-merge-gate.py` (PreToolUse, Bash): `gh pr merge <n>` needs a `## Review` block under `tasks/` that names the PR (`PR #n` or `owner/repo#n`) with a `verdict: pass` line dated today or yesterday (UTC); the last dated verdict in a file decides, so a later `fail` blocks. With `--repo`, the block must name that repo. After `MAX_REVIEW_ROUNDS` failing rounds the refusal says to stop and go to the owner. Fails closed | It reads the review; it cannot tell who wrote it, so an author can write their own pass. A merge through the web UI, or `git merge` + `git push`, is not seen. Without `--repo`, PR #12 of any repo matches. |
| A pasted client mail finds its history | `prompt-context.py` (UserPromptSubmit): a prompt with mail headers or a `CLIENT_CONTACT_EMAILS` address gets the ledger rows on that subject, the open asks and the open tasks as context | Subject-string match. A new subject gets only the open lists. |

## Gate modes

`.claude/gates.conf` sets `deny`, `warn` or `off` for `number-gate`, `claim-gate`, `subagent-stop`, `env-explicit`
and `read-gate`. `warn` writes what `deny` would have refused to `<state dir>/gate-warnings.log` and lets the call
through; `session-start.py` prints the count. A new fork starts on `warn`: read the log for a week, fix the false
positives, then move the gate to `deny`. Until then the four `warn` rows above are measurements, not enforcement.

The guards with no mode (`prod-guard`, `consent-guard`, `mail-guard`, `client-repo-guard`, `cred-scan`,
`pr-merge-gate`) always block.

## Where state lives

`<state dir>` is `~/.factory/<CLIENT_SLUG>/`, outside the repo: `consent/`, `evidence/`, `gate-warnings.log`,
`cred-scan.log`, `trigger-counts.json`. `FACTORY_STATE_DIR` and `FACTORY_ROOT` move the state and the repo root for
the tests only; `consent-guard.py` refuses a command that sets either.

## Only prose, not enforced

These are rules in `CLAUDE.md` and `RULES.md` with no hook behind them. They hold as long as they are read.

- **Research before any question to the client.** No hook knows whether the answer was already in the docs, the code
  or the mail history. `scripts/draft.py --ask` refuses unless the task's Research block ends in "Awaiting a specific
  answer", but only when the author passes `--ask`: a body that holds a question, drafted without it, passes.
- **One ask, once.** The hooks show the open asks (`session-start.py`, `prompt-context.py`). Refusing a repeated ask
  is the job of `scripts/draft.py --ask`, not of a hook, and only for mail made through it with that flag.
- **The fork's `factory.conf` is right.** The unit tests run on their own fixture and never read it.
  `scripts/check-conf.py` fails on an empty or placeholder value; it cannot tell that a marker is the wrong account.
- **"Blocked" and "cannot" are claims.** `claim-gate.py` asks for a command beside them in the state files. In chat,
  nothing checks them.
- **The reviewer is not the author.** `pr-merge-gate.py` needs a review block; it cannot see who wrote it.
- **Tests ran and passed.** `stop-check.py` wants some check after the last edit. It does not run the tests or read
  their result.
- **STATE.md is true.** Size and age are checked. Truth is not.
- **A mistake is recorded when it is found.** Nothing notices a mistake that nobody wrote down.
- **Scope: one file checked is one file checked.** No hook can tell a sample from the whole.
- **Production touched without a marker in the command.** A browser session, a default cloud profile, a deploy
  pipeline started by a push: none of these pass through `prod-guard.py`.
- **Anything done outside Claude Code.** The owner's phone, the web UI, another terminal.
