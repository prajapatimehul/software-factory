# STATE — NOW only, rewritten in place; every line stamped; outranks every note in the client repos

Stamp format: `[verified YYYY-MM-DD by <command | msgid | file:line>]`; `[recorded …]` = taken from a note, not re-run — a claim.
This file holds one dated NOW block and nothing else (at most STATE_MAX_LINES lines; the state check fails above it).
When the headline changes, the previous block moves to the top of STATE-LOG.md (newest first).
Per-task status: tasks/TASKS.md. Ids and addresses: REGISTRY.md.

## <WEEKDAY YYYY-MM-DD HH:MM UTC> — NEW FORK, NOTHING VERIFIED YET
[recorded YYYY-MM-DD by NEW-CLIENT.md step 4 — replace this block in the first session]
- **Prod:** <what is live, with the commit or version> [verified YYYY-MM-DD by <command>]
- **Dev:** <what is on the development side> [verified YYYY-MM-DD by <command>]
- **Mail:** <last message in or out, its msgid, whether a reply is awaited> [verified YYYY-MM-DD by <msgid>]
- **Open asks:** <ask ids from ledger/asks.tsv, or none> [verified YYYY-MM-DD by ledger/asks.tsv]
- **Promises due:** <promise ids and dates from ledger/promises.tsv, or none> [verified YYYY-MM-DD by ledger/promises.tsv]
- **In progress:** <task id — one line> [verified YYYY-MM-DD by tasks/T-NNN-….md]
- **Next:** <the one task to pick up next>
- **Watch:** <anything that must be looked at again, and when>
