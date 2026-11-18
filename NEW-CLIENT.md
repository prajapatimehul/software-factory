# NEW-CLIENT — fork steps for one new client

Budget about an hour. Do the steps in order: the hooks read `factory.conf`, so nothing is
protected until step 3 is done.

## 1. Fork and make it private

GitHub does not let a fork of a public repo be made private, so "fork" here means a private
copy that keeps the template as a second remote:

```bash
git clone https://github.com/prajapatimehul/software-factory.git <client-slug>-ops && cd <client-slug>-ops
git remote rename origin template
gh repo create <client-slug>-ops --private --source . --remote origin --push
```

Check before anything else is written: `gh repo view --json visibility` must say `PRIVATE`.

## 2. Put the client repos next to it

```
workspace/
  <client-slug>-ops/     this repo
  <client-app>/          the client's repo(s), cloned as siblings
  <client-data>/
```

## 3. Edit factory.conf

| Key | Set it to |
|---|---|
| `CLIENT_NAME`, `CLIENT_SLUG` | the client's name, and a short lowercase slug |
| `OWNER_NAME` | the person who keeps the two yeses |
| `CLIENT_REPOS` | the sibling paths from step 2, space-separated |
| `CLIENT_CONTACT_EMAILS` | every address that counts as the client |
| `OWNER_EMAIL` (optional) | the address of the mailbox `MAIL_CLI` is logged in to; saves one lookup call per draft |
| `MAIL_CLI` | the command that creates drafts in the mailbox you use for this client; see below |
| `PROD_MARKERS` | every string that means production in a command: full profile name, account id, full hostname |
| `DEV_MARKERS` | the same for development |
| `PRIVATE_WORDS` (optional) | extra words that must never be written into a client repo; the default is `timesheet billable do-not-chase` |
| `PROD_CONSENT_TOKEN`, `SEND_CONSENT_PHRASES`, `CONSENT_TTL_MIN` | keep the defaults unless you have a reason |
| `MAX_REVIEW_ROUNDS`, `STATE_MAX_LINES` | keep the defaults |

A missing production marker is the one mistake here that costs something: a command that does
not match a marker is not seen as production. List the account id and the profile name, and the
production hostname if there is one.

A marker is matched as a plain substring of the whole command, so it has to be distinctive. Do
not list a branch name or any short word: `main` also matches `domain`, `maintain` and
`src/main.py`, and each of those commands would then be refused as a production write.

`MAIL_CLI`: the scripts call it with `gws`-shaped arguments
(`gmail users drafts create --params '<json>' --json '<json>'`) and read JSON back. `gws` works
as it is. To pick an account through an environment variable write
`MAIL_CLI="env VAR=value gws"`; a bare `VAR=value gws` fails. Any other mail tool needs a small
wrapper script that takes the same arguments, and then the `gws gmail ...` lines under
`permissions.deny` in `.claude/settings.json` must be edited to name it.

`factory.conf` is the one config file. A fork also changes these, and step 8 commits them:

| File | What changes | Step |
|---|---|---|
| `.claude/rules/client-repos.md` | `paths:` set to the same repos as `CLIENT_REPOS` | now |
| `.claude/settings.json` | the mail deny list, only for a `MAIL_CLI` other than `gws` | now |
| `.claude/gates.conf` | which gates refuse (`deny`) and which only log (`warn`); leave it for the first week | 7 |
| `REGISTRY.md`, `TERMS.md`, `STATE.md`, `learning/glossary.md` | the client's facts | 4 |
| `docs/harness.md` | what the first-session checks showed on this fork | 7 |

## 4. Fill the templates

- `REGISTRY.md` — people, repos, accounts, resources. Paste each id from the tool that prints it.
  Secret names only, never values.
- `TERMS.md` — rate, budget, invoicing, each with its source.
- `STATE.md` — replace the placeholder block with one real NOW block. Stamp each line with the
  command that verified it. Leave out what you could not verify.
- `learning/glossary.md` — delete the example rows, or keep the ones that fit.
- `style/<contact>.md` — skip until there are five or six real exchanges to build it from.

## 5. Run the tests, then check your config

```bash
python3 -m unittest discover -s scripts/tests
python3 scripts/check-conf.py
```

The tests build their own throwaway root with their own `factory.conf`. Green means the hook and
script code works on this machine. It says nothing about your `factory.conf`.

`check-conf.py` reads your `factory.conf`. It fails when `CLIENT_REPOS`, `CLIENT_CONTACT_EMAILS`,
`PROD_MARKERS` or `DEV_MARKERS` is empty or still holds an `acme` placeholder, and it warns on a
marker that is short enough to match inside other words. It cannot tell that a marker names the
wrong account: read the markers it prints against `REGISTRY.md`.

Do not open a working session on a red run of either.

## 6. Open Claude Code at the root of this repo

```bash
claude --add-dir ../<client-app> --add-dir ../<client-data>
```

Open it here, not inside a client repo. Project settings load per project: a session opened
inside a client repo has none of the hooks. To skip the flags, list the repos under
`permissions.additionalDirectories` in `.claude/settings.local.json`.

## 7. First session checklist

Ask Claude to go through these in order and paste the output of each. Every command here is
harmless if its guard fails to stop it: the `echo` lines only print, because the guards match
the text of a command. Replace `<prod marker>` with one of your `PROD_MARKERS`.

- [ ] **Session start.** SessionStart printed a `--- state` line and the git status of each
      client repo. It does not read the mailbox.
- [ ] **Raw mail write is refused.** `echo gws gmail users drafts create` (use your `MAIL_CLI`
      program in place of `gws`) is refused by `mail-guard`.
- [ ] **Production write is refused.** `echo aws s3 rm s3://x/y --profile <prod marker>` is
      refused by `prod-guard`. Run it again with the consent token added by Claude
      (`... --profile <prod marker> PROD-WRITE-OK`): still refused, because the owner did not
      type the token. If either one prints instead of being refused, the marker in
      `factory.conf` does not match what you typed: fix it before anything else.
- [ ] **Unmarked cloud command is logged.** `echo aws s3 ls` goes through, and
      `tail -1 ~/.factory/<CLIENT_SLUG>/gate-warnings.log` shows an `env-explicit` line. It is
      not refused: `.claude/gates.conf` ships `env-explicit=warn`.
- [ ] **Private content into a client repo is refused.** Ask Claude to write a new file
      `<client repo>/factory-scratch.txt` with the content `see T-014`. `client-repo-guard`
      refuses before the file exists. If the file was created, delete it
      (`rm <client repo>/factory-scratch.txt`; it is untracked) and fix `CLIENT_REPOS`.
- [ ] **`/brief <any real question>`** fills a Research block that ends in an `Outcome:` line.
      `[not kept] mail archive` in its output is expected: a fork has no `mail/` directory
      unless you decide to save raw mail under `mail/raw/`.
- [ ] **A draft reaches the right mailbox.** `draft.py` refuses any To address that is not in
      `CLIENT_CONTACT_EMAILS` and needs a task file, so:
      1. `cp tasks/TEMPLATE.md tasks/T-000-setup-check.md`
      2. add an address of your own to `CLIENT_CONTACT_EMAILS` in `factory.conf`
      3. write one line with no claim in it to `tasks/drafts/setup-check.txt`, for example
         `Hello, this is a setup check. Please ignore it.`
      4. `python3 scripts/draft.py --dry-run --task T-000 --new-thread --subject "Setup check" --to <your address> --body-file tasks/drafts/setup-check.txt`
         must end in `dry run: every gate passed`
      5. the same command without `--dry-run` prints a draft id; look at the draft in the mailbox
      6. `python3 scripts/draft.py --delete <draft id>`
      7. remove your address from `CLIENT_CONTACT_EMAILS`, delete the task file and the body
         file, and check that `ledger/mail.tsv` has no `draft:` row left
- [ ] `python3 scripts/mistakes.py counts --write` leaves `RULES.md` unchanged (all `0 / 0`).
- [ ] `/checkpoint` rewrites STATE.md and `bash scripts/check-state.sh` exits 0.

If a refusal check does not refuse, stop and fix it before real work. Write what you found into
`docs/harness.md`: that table has to describe this fork, not the template.

**Gate modes.** `.claude/gates.conf` ships `number-gate`, `claim-gate`, `subagent-stop` and
`env-explicit` on `warn`: they log to `~/.factory/<CLIENT_SLUG>/gate-warnings.log` and stop
nothing. Session start prints the count. Read the log for the first week, fix the false
positives, then set each gate to `deny`.

## 8. Commit

```bash
git add factory.conf REGISTRY.md TERMS.md STATE.md learning/glossary.md docs/harness.md \
        .claude/rules/client-repos.md .claude/gates.conf .claude/settings.json
git commit -m "Configure for <client-slug>"
git push
```

## Day two and after

- Start: read the SessionStart output, pick the task, open its file.
- New mail: paste it, or run `python3 scripts/inbox-sweep.py` to list what the ledger does not have yet. It gets a
  ledger row and a task before anything is written back.
- New domain fact: `learning/LEARNING.md`, the same day.
- Mistake: record it when found, `scripts/mistakes.py new …`.
- Stop: `/checkpoint`.

To pull later improvements from the template: `git fetch template`, then cherry-pick what you want. Do not merge blindly: `factory.conf`,
STATE.md, the ledgers and `learning/` are yours.
