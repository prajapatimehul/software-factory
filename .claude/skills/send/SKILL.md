---
name: send
description: Send a draft that scripts/draft.py created. Only the owner invokes this; Claude never sends on its own.
disable-model-invocation: true
---
# /send <draft-id>

Run `python3 scripts/send.py --draft-id <id>`. It works only while the owner's own send instruction is live (this
command typed by the owner, or one of SEND_CONSENT_PHRASES in their prompt, within CONSENT_TTL_MIN). It re-checks the
thread for the same content sent today, sends, and replaces the ledger row with the real message id.

If it says REFUSED: report the reason and stop. Do not retry, and do not look for another way to send.
After a send: `/checkpoint` (task file `## Sent / drafted`, STATE.md, ledgers).
