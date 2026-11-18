# software-factory

A Claude Code harness for running one client engagement as a light software factory.

Agents do the building, the reviewing and the testing. A human keeps two decisions: a write to
production, and a mail to the client. Everything else in this repo exists to make those two
decisions safe to give quickly.

Fork it once per client. The fork is private; the client never sees it. It sits next to the
client's own repos and holds what an engagement needs besides code: the current state, the
tasks, every message in and out, what was promised, what was claimed, what was learned, and
every mistake with the rule it produced.

"Light" means there is no server, no queue and no scheduler. It is a folder of Markdown and TSV
files, Python standard-library scripts, and Claude Code hooks. You open a session, paste a mail
or name a task, and the loop below runs.

## The loop

```
mail or task
   -> brief     search our own files, the code and the cloud before any question
   -> work      in the client repo; command + output go into the task file as you go
   -> review    a separate reviewer agent grades the change; the author never does
   -> verify    "done" needs a command that could have shown it was not done
   -> draft     a reply is created as a draft, never sent
   -> the human reads it and says "send it"
```

| Step | Command | What it leaves behind |
|---|---|---|
| Mail arrives | paste it; `/task` records it with `scripts/inbox-sweep.py --record` | a row in `ledger/mail.tsv`, a task in `tasks/` |
| Brief | `/brief <topic>` | the task's Research block, ending in an `Outcome:` line |
| Work | normal Claude Code work in a client repo | `cmd:` lines in the task's Evidence section |
| Review | reviewer agent, at most `MAX_REVIEW_ROUNDS` rounds | the task's Review section |
| Verify | `/verify` | fresh evidence, or a list of what is still unproven |
| Draft | `/reply` | a draft in the mailbox, rows in `ledger/` |
| Send | the owner types a send phrase, then `/send` | the sent msgid in `ledger/mail.tsv` |
| Stop | `/checkpoint` | STATE.md rewritten, the old block moved to STATE-LOG.md |

## The two yeses

- **Production.** A command that carries a production marker and writes is refused unless it
  contains `PROD-WRITE-OK` and the owner typed that word in their own prompt in the last
  15 minutes. The agent typing the word does not count.
- **Client mail.** The agent can only create drafts. Sending needs the owner to type "send it".

The token, the phrases and the time window are set in `factory.conf`.

## Enforced, or only written down

A rule in a prompt is a request. A hook is a gate. This repo tries to be exact about which is which.

Enforced by a hook or a script gate (it stops the action):

- sending mail, or writing to the mailbox outside `scripts/draft.py` and `scripts/send.py`
- a production write without the token and the owner's live consent
- writing private content into a client repo
- a draft declared as a question (`draft.py --ask "<wording>"`) before the task's Research block allows it, or
  when the same ask is already open in `ledger/asks.tsv`
- merging a PR with `gh pr merge` when no passing review is on record
- commands matching a row in `learning/triggers.tsv` (known mistakes, one regex each; refused once, then let through)

Measured, not enforced, until you set the gate to `deny` in `.claude/gates.conf` (a new fork ships these on `warn`:
the call goes through and a line goes to `~/.factory/<slug>/gate-warnings.log`):

- a cloud command that names neither production nor development (`env-explicit`)
- a number written into a state, task or ledger file that no tool printed in this session (`number-gate`)
- a claim word in those files with no command beside it (`claim-gate`)
- a subagent report with numbers or claims its own transcript does not hold (`subagent-stop`)

Only prose (Claude is told, nothing checks):

- Rule 0, "prove it before you say blocked", beyond what the brief step forces
- a question to the client in a draft made without `--ask`: the ask gates run only when the author declares the ask
- task first, tooling later
- the tone and shape of a mail, beyond the word lists in the draft gate

`docs/harness.md` is the full table: expectation, mechanism, and the limit of each mechanism.
Every gate has a limit, and the table says where each one stops. Read it before trusting any of
them, and keep it true when you change one.

## What is in the box

```
CLAUDE.md        Rule 0, the seven rules, what to do first, what to do before "done"
RULES.md         twelve mistake shapes, each with its rule, its mechanism and a count
STATE.md         now, and only now; every line stamped with how it was verified
STATE-LOG.md     where old state goes
factory.conf     the one config file; NEW-CLIENT.md lists the other files a fork fills in
REGISTRY.md      ids, accounts, resources, secret names
TERMS.md         commercial facts
tasks/           one file per task, with Research, Evidence and Review sections
ledger/          mail, asks, promises, claims as TSV
learning/        domain facts from the client, mistakes, a glossary, trigger regexes
decisions/       one file per decision
style/           how to write to each contact
docs/harness.md  the honesty table
.claude/         settings, gate modes (gates.conf), hooks, skills, agents, path-scoped rules
scripts/         draft, send, consent, mistakes, state check, config check, and their tests
```

## Why mistakes get a file

Every mistake is recorded when it is found, including the ones caught before anyone saw them.
Each one is filed under one of twelve shapes ("a claim without the command that could falsify
it", "the check could only confirm what was expected", "fixed one thing, missed its sibling").
`scripts/mistakes.py` keeps the count per shape in `RULES.md`. When a shape keeps growing, it
gets a mechanism: a regex in `triggers.tsv`, a gate in a script, or a hook. The counts start at
zero in a new fork. The shapes come from real client work.

## Quick start

Requirements: Claude Code, Python 3 (standard library only), git, the GitHub CLI `gh` (the private copy below and
the merge gate both use it), and a mail CLI. The mail scripts call `MAIL_CLI` with `gws`-shaped arguments and read
JSON back, so `gws` works as it is and any other tool needs a small wrapper (see the comment beside `MAIL_CLI` in
`factory.conf`).

```bash
git clone https://github.com/eagerminds-ai/software-factory.git acme-ops && cd acme-ops
git remote rename origin template
gh repo create acme-ops --private --source . --remote origin --push   # a private copy per client
$EDITOR factory.conf                                    # client, repos, contacts, markers
python3 -m unittest discover -s scripts/tests           # the gate code, tested offline on a fixture
python3 scripts/check-conf.py                           # your factory.conf: no empty marker, no placeholder
claude --add-dir ../acme-app --add-dir ../acme-data
```

Then follow [NEW-CLIENT.md](NEW-CLIENT.md) for the first session.

## What it is not

- Not autonomous. Nothing starts by itself and nothing reaches production or the client without
  a person. That is the design.
- Not a framework. There is nothing to install or import. Read the files, change them, delete
  what the engagement does not need.
- Not a guarantee. Hooks match patterns, and a pattern can be missed. `docs/harness.md` lists
  the known gaps.

## Credit and license

Built at eagerminds from a harness used on real client work, with every client detail removed.
MIT, see [LICENSE](LICENSE).
