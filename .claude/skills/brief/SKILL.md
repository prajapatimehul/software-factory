---
name: brief
description: Run before ANY question to the client, and whenever a task starts. Greps every local source (state, tasks, ledgers, decisions, learning, mistakes, the client repos) for the topic and ends in one of five outcomes; only "Awaiting a specific answer" permits a question.
---
# /brief <topic>

1. Run `bash scripts/brief.sh "<topic>" "<alt|words>"`. Alt words are the client's own words for the thing and ours.
   Read every `[ok N]` hit that could matter. An `[UNAVAILABLE]` source means the search is incomplete until that
   source is opened another way. `[not kept] mail archive` is not a gap: this fork saves no raw mail under
   `mail/raw/`, so read the thread in the mailbox when the ledger rows point to one.
2. If the topic is how a vendor or platform behaves: read the vendor's own doc page. Do not guess. If a call failed,
   read its error document first.
3. If the topic is the state of a live system: run the read-only call that answers it, with the environment named
   explicitly (`.claude/rules/cloud.md`).
4. Write the `## Research` block in the task file: sources checked with their counts, what was found
   (file:line, URL or command), and exactly one closing line:
   - `Outcome: Answered` — proceed, no question.
   - `Outcome: Deferred` — not needed now; say why.
   - `Outcome: Conflicting` — two sources disagree; run the command that settles it, then brief again.
   - `Outcome: Awaiting a specific answer` — the ONLY outcome under which `/reply` may carry a question. It needs:
     the missing fact in one sentence; why only the client can give it (an input only they have, their authority, a
     change of scope); the default we assume if they do not answer; the work already done that did not depend on it.
   - `Outcome: Search incomplete` — never a question. Finish the search.
5. `ledger/asks.tsv`: if the same ask is `open` or `do-not-chase`, the outcome is Deferred, whatever step 4 said.
