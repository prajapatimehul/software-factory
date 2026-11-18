# LEARNING.md — domain knowledge from the client

What this is for: the client knows their business, we know the code. Every time they explain how
their domain really works, it goes here, with the date and their words where the words matter.
Re-read it (through `LEARNING-INDEX.md`) before designing anything that touches their data, so the
same thing is not re-derived, or asked twice.

Rules:

- Append-only, dated, with the source: a msgid, a call date, or a file:line.
- A domain fact goes here the same day it is learned. A fact we found ourselves the hard way
  (a schema that drifts, a job that lags) belongs here too, with the command that showed it.
- Tasks, deadlines and preferences do not go here. Tasks live in `tasks/`, promises in `ledger/`,
  decisions in `decisions/`, how a person likes to be written to in `style/`.
- Quote the client when the exact wording carries the meaning. Do not tidy their words.
- A fact that turned out wrong is not edited: append a new entry that names the old label.
- After appending, add the row to `LEARNING-INDEX.md`.

Entry shape:

    ## <label>. <the fact, as one sentence> (YYYY-MM-DD)
    Source: <msgid | call YYYY-MM-DD | file:line | command>
    > "<their words, if they matter>"
    What it means for our work: <one to three lines>
    Checked how: <command and result, or "not checked — their statement">

---
