# MISTAKE.md — what went wrong, and why

Append-only. Every mistake goes here the moment it is found, with the root cause and the rule that
would have prevented it. That includes a mistake caught before it reached anyone. Not a list of
apologies: the same shape of error keeps coming back, and the shapes (RULES.md, P1..P12) are more
useful than the incidents.

How to add one:

1. Tell the owner first, plainly: what was claimed, what was true, why it was believed, what it cost.
2. `scripts/mistakes.py new --shape P<n> --caught-by … --reached … --actor … --summary "…"` plus one of
   `--trigger <regex>`, `--mechanism <name>` or `--prose-only`. It appends the heading and a skeleton
   below, adds the row to `mistakes.tsv`, and rewrites the counts in `RULES.md`.
   `scripts/mistakes.py new --help` lists the allowed values.
3. Fill the skeleton. Short and specific beats long.
4. If a regex could have stopped it, the entry is not finished until the row is in `triggers.tsv`.

How to read one: `scripts/mistakes.py show N`. Do not read this file whole once it has grown.

Entry skeleton (the script writes it; the heading is two hashes, the entry number, a dot, the title):

    <heading line>
    *YYYY-MM-DD. Caught by <who or what>. Reached <nobody | a file | the owner | a draft | the client | prod>.*

    **What happened.** What was claimed or done, and what was actually true.

    **Why.** The real cause. "Was not careful" is not a cause.

    **Impact.** What it cost, or would have cost: hours, money, a wrong mail, a production change.

    **Rule.** The one line that prevents it, and where that line now lives
    (a hook, a script gate, a triggers.tsv row, or prose in CLAUDE.md).

Never edit or delete an old entry. A correction is a new entry that names the old one.

---
