---
name: checkpoint
description: Land the work before stopping or when a task changes state. Updates the task file, the NOW block of STATE.md (history goes to STATE-LOG.md), TASKS.md and the ledgers, then commits this repo by path. Use after every draft, send, finding or decision.
---
# /checkpoint

1. Task file: `status:`, `## Evidence` (dated cmd lines), `## Sent / drafted` (ask ids, msgids), `## Open`, `## Next`,
   `## What did NOT work`. Keep it under about 150 lines; older history moves to the bottom or to `tasks/archive/`.
2. `STATE.md` holds NOW only (at most STATE_MAX_LINES lines): one dated block, every line stamped
   `[verified YYYY-MM-DD by <command | msgid | file:line>]`, one `- **Next:**` line. Rewrite the block in place. When
   the headline changes, move the previous block to the TOP of `STATE-LOG.md` (newest first; never read whole).
   Every number and time in it is copied from a tool output of this session.
3. `tasks/TASKS.md`: the row equals the file's status. `ledger/*.tsv`: asks answered → `answered` + the answering
   msgid; promises kept → `done` + evidence; a claim told to the client → a row in `claims.tsv` with its verify command.
4. A domain fact from the client → `learning/LEARNING.md`, dated, with its source. A decision → `decisions/`.
   A mistake → say it plainly to the owner first, then
   `python3 scripts/mistakes.py new --shape P… --caught-by … --reached … --actor … --summary "…" (--trigger RE | --mechanism NAME | --prose-only)`,
   fill the skeleton in `learning/MISTAKE.md`, then `python3 scripts/mistakes.py counts --write`. Nothing is bumped by hand.
5. `bash scripts/check-state.sh` must exit 0. Then commit by path, never `git add -A`:
   `git add STATE.md STATE-LOG.md tasks/ ledger/ learning/ decisions/ RULES.md` and `git commit -m "<what changed>"`.
   Push only if the owner has asked for pushes in this repo.
