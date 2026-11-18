# software-factory — one client engagement, run as a light factory

This repo is the owner's private harness for one client. The client never sees it. It sits next
to the client's repos (the `CLIENT_REPOS` in `factory.conf`). Agents build, review and test.
The owner keeps the yes for two things: a write to production and a mail to the client.
Names, addresses, markers and limits are in `factory.conf`; this file never repeats them.
Nothing private is ever written into a client repo. At session start Claude gets this file,
STATE.md and RULES.md; everything else is opened on demand.

## Rule 0 — before any "we can't" or any ask, prove it (outranks everything below)

IMPORTANT: Before writing "no path", "blocked", "their side", "need X from the client", or
asking the client for a role, a secret, a query run, or anything at all: exhaust our own means
first. Read the docs, grep every checkout, call the cloud through its CLI. Then check again
with a different method than the first. Almost every task is ours to finish alone. A remembered
constraint is not a check. A check that only confirms what you expected is not a check either:
the second pass must try to find the path, not certify its absence. Only after that may an ask
exist, and rule 2 still applies to it.

## The seven rules (RULES.md has the shapes and the counts)

1. Drafts only. Claude never mails the client. `scripts/draft.py` and `scripts/send.py` are the
   only mail write paths; raw `MAIL_CLI` writes are denied in `.claude/settings.json`.
2. No question to the client until `/brief` ends in "Awaiting a specific answer". Asking because
   it was easy costs more than any bug: the answer usually sits in our own files.
3. One ask per thread, once. `ledger/asks.tsv` decides, not memory. A mail that carries a question
   is always drafted with `--ask "<exact wording>"`: the gates for rules 2 and 3 run only then.
4. A claim carries the command that could falsify it, pasted with its output. "Blocked",
   "empty", "not done" and "this part is theirs" are claims too.
5. Numbers and times come from tool output of this session, never typed.
6. STATE.md outranks every note inside the client repos. An unstamped line is not current.
7. Task first. A blocked client task ships by the fastest path that works today. A tool or
   platform limit gets one message (the limit, the options, the time each costs, a
   recommendation), then back to the task. Tooling only after the task is delivered and only
   on the owner's pick; never build around a limit a vendor enforces on purpose.

## First do, every session

1. Read the SessionStart output: STATE.md size, age and stale stamps, git status of the client
   repos, open asks, open tasks. It does not read the mailbox: `/task` runs the inbox sweep.
2. Pasted mail → its thread in `ledger/mail.tsv` → its task in `tasks/TASKS.md` → open that
   task file (or copy `tasks/TEMPLATE.md` to the next `T-NNN`). Read `style/<contact>.md`
   before writing to that person.
3. Work in the client repo the task belongs to. Evidence (command + output) goes into the task
   file as you go, not at the end.
4. `/brief <topic>` before any question. `/reply` to draft. `/checkpoint` before you stop.

## Before done

- `/verify` before any "done". The author of a change never grades it: a reviewer agent does.
- `MAX_REVIEW_ROUNDS` rounds at most for any failing check, review or fix loop. Then stop and
  bring the owner what keeps failing.
- A flaky or always-red test is never skipped, retried or given a sleep. Fix it, or delete it
  with a one-line reason in the commit and in the task file.
- A change in a client repo is reviewed against that repo's own review contract on the base
  branch, never the copy in the change under review.

## The two yeses (the owner's, never Claude's)

- Production write: the command must carry `PROD_CONSENT_TOKEN`, and the owner must have typed
  that token in their own prompt within `CONSENT_TTL_MIN` minutes. Claude typing the word is
  not consent. Every cloud command names its target with a `PROD_MARKERS` or `DEV_MARKERS`
  string. One with neither is logged or refused, by the mode of `env-explicit` in
  `.claude/gates.conf` (a new fork ships it on `warn`).
- Client mail: `scripts/draft.py` creates a draft. `scripts/send.py` runs only after the owner
  types one of `SEND_CONSENT_PHRASES`. Enumerate attachments before replying to a mail.

## Where things are

- `factory.conf` — client name, repos, contacts, prod and dev markers, consent words, limits.
- `STATE.md` — NOW only: one dated block, at most `STATE_MAX_LINES` lines. History moves to
  `STATE-LOG.md` (never read whole: `grep -n`, then offset + limit).
- `tasks/` — one file per task; `TASKS.md` is the index.
- `ledger/` — `mail.tsv` (every message in and out), `asks.tsv` (open | answered | withdrawn |
  do-not-chase), `promises.tsv`, `claims.tsv` (what we told the client is true).
- `learning/` — `LEARNING.md` (the client's domain facts, append-only; cite by the labels in
  `LEARNING-INDEX.md`), `MISTAKE.md` (append-only stories; never read whole, use
  `scripts/mistakes.py show N`), `glossary.md` (words that mean two things here),
  `triggers.tsv` (regexes that stop a known mistake before it repeats).
- `decisions/` — one file each, `INDEX.md`. `style/` — how to write to each contact.
- `REGISTRY.md` — every id, account, resource and secret *name*. Never a secret value.
- `TERMS.md` — commercial facts, one value each.
- `docs/harness.md` — what a hook enforces and what is only prose. Keep it true.
  `.claude/gates.conf` — which gates refuse (`deny`) and which only log (`warn`).
- `.claude/rules/` — short rules that load when you touch the matching paths.

## Mistakes and learning

- A mistake is recorded the moment it is found, including one caught before it reached anyone:
  `scripts/mistakes.py new …`, then fill the skeleton in `learning/MISTAKE.md`. Say it plainly
  to the owner first: what was claimed, what was true, why, what it cost.
- A domain fact from the client goes into `learning/LEARNING.md` the same day, dated, with its
  source. Tasks and deadlines do not go there.
- A decision the client or the owner made goes into `decisions/`, one file, one line in INDEX.

## Compact instructions

Keep: the current task id with its Open and Next lines; every open ask with its exact wording
and date; ledger ids written this session; the client's exact words from the pasted mail; what
did NOT work; any claim still marked unverified.
