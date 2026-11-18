---
name: reply
description: Draft the reply to a client mail. Reads the mail and its attachments, checks the ledgers, writes the body to a file in the contact's style and creates a DRAFT through scripts/draft.py. Never sends.
---
# /reply

1. Read the whole mail: headers, EVERY attachment name, the body, and any inline replies inside the quoted text.
   List the client's direct questions; each one is answered or explicitly deferred before anything else is said.
2. Find or create the task (`/task`). For every claim the reply will make, put today's line in `## Evidence`:
   `- YYYY-MM-DD cmd: <command> → <output>`. No command, no claim. "Blocked", "empty" and "this part is yours" are
   claims too.
3. Read `style/<contact>.md`. Write the body to `tasks/drafts/<task>-<date>.txt`: the answer first, numbers copied
   from Evidence, what they can open or look at, at most one ask (only if the Research outcome is "Awaiting a specific
   answer"), 180 words at most, no option menu, no tool names.
4. If the body has a claim, or says how something works: spawn the `work-reviewer` agent on THIS body with the task
   file path. Paste its block into the task file under a heading that names the body file
   (`## Review — <date> <time> UTC — scope: <body file name>`). Fix what it finds. The author never grades the author.
5. Check first with `--dry-run`, then create the draft:
   `python3 scripts/draft.py --task T-NNN --thread <threadId> --reply-to <msgid> --body-file tasks/drafts/… [--ask "<exact wording>"]`
   A body that holds a question always gets `--ask`: without it the research gate and the repeated-ask gate do not run.
   A REFUSED names its cause. Fix the cause; never work around the gate.
6. Tell the owner: the draft id, the To and Cc, the word count, and paste the body. The owner sends with `/send`.
   Then `/checkpoint`.
