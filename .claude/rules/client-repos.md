---
paths:
  - "../acme-app/**"
  - "../acme-data/**"
---
# Client repos — the client's code, their rules (set `paths` to the CLIENT_REPOS of this fork)
- Nothing private crosses over: no ledger rows, task ids, mistake numbers, state notes or draft text in code,
  comments, commit messages, branch names or PR bodies.
- `git fetch`, then branch from the remote development branch. Never from a local branch or another feature branch.
- `git add` by path. Never `-A`, `--all` or `.`.
- A PR always names its base branch. The production branch moves only through a release PR, never a direct push.
- Read the repo's own README, contributing notes and review contract before the first change. Theirs outrank ours inside their repo.
- A note inside a client repo that disagrees with STATE.md is stale. STATE.md wins; say so in the task file.
