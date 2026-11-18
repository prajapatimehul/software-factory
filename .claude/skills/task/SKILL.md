---
name: task
description: Start work from a pasted client mail or an instruction. Finds the thread and the task, or opens a new T-NNN from the template, and sets up the research and evidence sections before any work.
---
# /task

1. Find what exists: `grep -i "<words>" tasks/TASKS.md ledger/mail.tsv ledger/asks.tsv`. A pasted mail belongs to a
   thread in `ledger/mail.tsv`; the thread belongs to a task.
2. Existing task: open it and read `## Open`, `## Next` and `## What did NOT work` before anything else.
   New task: `cp tasks/TEMPLATE.md tasks/T-NNN-<slug>.md` (next free number in `tasks/TASKS.md`), fill source, thread
   and goal, add the index row. Is something already half done for the same goal? Finish or close that first.
3. Record the inbound mail: `python3 scripts/inbox-sweep.py --record`, then set the `task` column of its row.
   List every attachment by name before reading the body; save the ones the work needs outside the client repos.
4. Fill `## Population` before a fix: every field, path, role, table or count the change could touch.
5. `/brief <topic>` before deciding anything. Then work in the client repo the task belongs to; evidence
   (`- YYYY-MM-DD cmd: … → …`) goes into the task file as you go.
6. End with `/verify` (before any "done"), `/reply` (if a reply is due) and `/checkpoint`. If the outcome is "we need
   to ask the client X", the Research block says so and the draft carries exactly that one ask.
