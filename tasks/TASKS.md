# TASKS — index, one row per task file. The task file is the record; this row is a pointer.

New task: copy `TEMPLATE.md` to `T-NNN-<short-slug>.md` (next free number), then add its row here.
The status here must equal the `status:` line in the file; the state check compares the two.
A done task keeps its row. Move rows older than a quarter to `archive/TASKS-<year>.md` if the table gets long.

| id | status | title | source | due | file |
|---|---|---|---|---|---|
