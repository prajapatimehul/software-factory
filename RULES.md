# RULES — the mistake shapes, one line each; counts are written by `scripts/mistakes.py`, never by hand

Rule 0 (CLAUDE.md): before any "can't / blocked / theirs / ask" — docs, every checkout and the cloud CLI first, then a
second method that tries to FIND the path. Only then may an ask exist, and rule 2 still applies.

Read a story: `scripts/mistakes.py show N`. Record one: `scripts/mistakes.py new --shape P5 --caught-by … --reached …
--actor … --summary "…" --trigger RE | --mechanism NAME | --prose-only`, then fill the skeleton in learning/MISTAKE.md.
Never read learning/MISTAKE.md whole once it has grown. Counts = primary / involved, from learning/mistakes.tsv.

<!-- counts:begin -->
| # | Shape | The rule | Mechanism | primary / involved |
|---|---|---|---|---|
| P1 | Claim without the falsifying command | A claim line carries the command that could falsify it, pasted with its output. "Blocked", "empty", "done", "live", "theirs" and "all of them" are claims. | draft.py claim gate (mail); claim hook (warn); Stop hook: done needs proof (blocks once) | 0 / 0 |
| P2 | A number or time felt or typed | Every number and time is copied from a tool output of this session; a derived one shows its inputs and the word computed. | number hook over the session evidence log (warn) | 0 / 0 |
| P3 | Stale state reported as current | STATE.md holds "now" only, every line stamped; a stamp older than 7 days is re-verified before it is repeated. | scripts/check-state.sh at /checkpoint: stamps + STATE_MAX_LINES; session start prints the stale-stamp count (prints, never blocks) | 0 / 0 |
| P4 | Typed from memory, not copied from the source of record | Ids, options, ports, formats and epochs are pasted from the source, never retyped or cut by character position; a time gets a "Z" only after it was converted to UTC. | number hook (warn); learning/triggers.tsv rows (refused once) | 0 / 0 |
| P5 | The check could only confirm what was expected | Write the expected value before the command; an empty / absent / 0 result needs a must-match control; one cell is not a matrix; the author never grades the author. | reviewer agent (prose) + draft.py review gate; empty-result hook (reminder); subagent hooks (warn) | 0 / 0 |
| P6 | Fixed one thing, missed its sibling | Before a fix, list the population (every field, path, role, principal, table, count) in the task file and check one more member than the one that broke. A resource policy is added to, never rewritten. | reviewer agent, siblings lens (prose); learning/triggers.tsv rows (refused once) | 0 / 0 |
| P7 | Asked the client before exhausting our own means | No question until `/brief` ends "Awaiting a specific answer". | /brief (prose); draft.py ask gate, only for a draft made with `--ask` | 0 / 0 |
| P8 | Client mail handled wrongly | One ask per thread, once (ledger/asks.tsv); enumerate attachments; answer every open question; read To/Cc back from the mailbox. | draft.py gates (the ask gates only with `--ask`); inbox sweep (a script /task runs, not a hook) | 0 / 0 |
| P9 | Wrong place or wrong window | Logs never in /tmp; no heavy job inside the production batch window; `git add` by path; a log look-back starts after the previous call. | .claude/rules/ (prose); learning/triggers.tsv row `git-add-all` (refused once) | 0 / 0 |
| P10 | Private content in a client-visible repo | Nothing private crosses into any of the CLIENT_REPOS. | client-repo guard hook | 0 / 0 |
| P11 | A wrong number fixed by removing its surface | A wrong figure is fixed in place; the card, chart or column stays. | reviewer agent, surfaces lens (prose) | 0 / 0 |
| P12 | Tooling before the task | A blocked client task ships first, by the fastest path that works today (the laptop counts). A platform limit gets ONE message: the limit, the options, the time each costs, a recommendation. Tooling work starts only after the task is delivered and only if the owner picks it; never tooling around a limit the vendor enforces on purpose. | prose (CLAUDE.md rule 7) | 0 / 0 |
<!-- counts:end -->

The "Mechanism" column is a pointer. An entry with no suffix refuses the action. `(warn)` logs and lets it through
until its gate is set to `deny` in `.claude/gates.conf`; `(refused once)` and `(blocks once)` pass on the retry;
`(prose)` and `(reminder)` stop nothing. `docs/harness.md` is the record of what each mechanism really stops and where
it stops short. When the two disagree, fix this column.

Two standing shapes that come from the mail side, not from entries: a blocker blamed on the client's setup is often
wrong, so a mail that blames their side carries the test already run; and inbound client questions get lost, so
`/reply` lists the questions in the mail and answers or defers each one.

Adding a shape: only when three entries fit none of P1..P12. Add the row inside the counts block with `0 / 0`,
then run `scripts/mistakes.py counts --write`.
