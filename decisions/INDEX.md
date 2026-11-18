# decisions — one file each; newest last. Open the file, do not load the directory.

A decision is something the client or the owner settled that later work depends on: scope, who owns
what, which branch deploys where, what may be done without asking. File name: `D-NNN-<short-slug>.md`.

Each file holds: the decision in one sentence, the date, who made it, the source (msgid, call date),
their exact words if short, and what it replaces. A reversed decision is not edited: write a new
file and mark the old row `superseded by D-NNN`.

| id | date | decision |
|---|---|---|
