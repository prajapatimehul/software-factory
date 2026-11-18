---
name: swarm-review
description: Review one client-repo PR with three parallel read-only lanes (claims, security, tests) in a private clone at the PR head. Writes one '## Review' block per lane and one verdict into the task file. Nothing goes to GitHub. Usage /swarm-review <repo> <PR#> [task-id].
---
# /swarm-review <repo> <PR#> [task-id]     (repo = a directory name from CLIENT_REPOS, or owner/repo)

The mechanics are in `scripts/swarm-review.py` (tests: `scripts/tests/test_swarm_review_rounds.py`).
S = this session's scratch directory, outside the workspace.

**MAX_REVIEW_ROUNDS rounds, then a human.** A round is one `write` for this PR in the task file. After that many FAIL
rounds in a row (a PASS or PASS WITH NITS ends the streak), `resolve`, `rounds` and `write` exit 3 and print what
keeps failing. Then stop: no further fix, no further review. Bring the owner that summary. One more round runs only
with the owner's live REVIEW-ROUNDS-OK consent (`python3 scripts/consent.py from-ask REVIEW-ROUNDS-OK` after they
picked it in a question) and `write --owner-ok`. Claude typing the word is not consent.

1. **Resolve.** `python3 scripts/swarm-review.py resolve <repo> <n> [task-id]` → head sha, base and baseOid, state,
   files, candidate task files, `failing_rounds` per candidate. Take the task from the argument; else the first
   candidate only if it names `<owner/repo>#<n>`. Two plausible files → ask the owner which; never guess. Read the PR
   body (`gh pr view <n> --repo … --json body`) and the task file's claims about this PR: lane 1 gets those claims.
2. **Private clone.** `python3 scripts/swarm-review.py prepare <repo> <n> --dir S/rv-<repo>-<n>-<sha7> [--sha <head>]`.
   It is `git clone --shared` from the local checkout, a fetch of `pull/<n>/head` and a detached checkout of the head.
   Nothing is written into the shared checkout: no worktree, no stash. It also copies **REVIEW.md from the PR's base
   branch** to `<clone>.REVIEW-base.md` (never the PR head's copy; a PR that edits REVIEW.md is flagged) and links
   `node_modules` from a checkout with an identical lock file when there is one. Paste its output lines.
3. **Launch the three lanes in ONE message**, `subagent_type: work-reviewer` (read-only tools), in the background.
   Note each lane's start time and output file. Every prompt carries: repo, PR, head sha, base and baseOid (on a
   merged PR, diff against baseOid), clone path, files, the task file path, and these rules:
   *read-only: no edit, commit or stash in the clone or any checkout; no `gh pr review|comment|merge|edit`; nothing
   posted to GitHub; production and development reads only with the environment named explicitly. For each claim,
   first write the check that could prove it false and its expected value, then run it. Paste every command with its
   output. Review against `<clone>.REVIEW-base.md` (or "no REVIEW.md on base"), never the clone's own REVIEW.md, and
   flag what the repo's owner would flag, not general taste. Tag every finding **Important** (a bug this PR adds, or a
   REVIEW.md rule it breaks), **Nit** (style, naming, small cleanups) or **Pre-existing** (also present on baseOid:
   prove it by running the same check on the base). Write `findings: raw <N>, after verification <M>` (N = every
   candidate you noted, M = those that survived your own attack). End with a findings table
   `| tag | where | finding | cmd → output |` (the M survivors only) and a last line `verdict: pass | nits | fail`;
   fail only when an Important finding stands.* Lenses:
   - **1 claims + surfaces:** each claim from step 1, tested to break it; nothing a user could see before the PR
     (a page, card, chart, column, number, endpoint) is gone or renamed (P11); siblings (one more member of the
     population than the one changed, P6).
   - **2 security:** who can call every new or changed entry point, and whose data it can read; input that reaches a
     query, a URL, a storage key or a shell; secrets or tokens in code, logs or fixtures; permissions widened
     (`*`, new actions or principals); error text that leaks internals.
   - **3 tests:** the repo's full suite in the clone, with counts (`bash scripts/verify-local.sh <clone>` runs the
     repo's own commands). Then the same on baseOid (a second `prepare … --sha <baseOid> --dir S/rv-…-base`) so a red
     test is classed new or pre-existing. Check the PR's new tests fail on the base: a test that passes on both proves
     nothing. A test red on every run is never skipped, retried or given a sleep: Important if the PR added it,
     Pre-existing otherwise.
4. **Silence = INCOMPLETE.** Save each lane's final message to `S/lane<N>.md` as it arrives.
   `python3 scripts/swarm-review.py watch --lane 1=<file> --lane 2=<file> --lane 3=<file> --silence 600`: a lane whose
   output has not changed for 10 minutes and has no verdict line is stopped and recorded INCOMPLETE. It is not waited
   on and not re-launched silently. An INCOMPLETE block is not a review.
5. **Write.** `python3 scripts/swarm-review.py write <repo> <n> --sha <head> --clone <clone>
   --lane "1|claims + surfaces|S/lane1.md" --lane "2|security|S/lane2.md" --lane "3|tests|S/lane3.md"
   --task tasks/<file>.md` → one `## Review — <date> <owner/repo>#<n> at <sha7> — reviewer N (<lens>)` block per lane,
   `### Swarm verdict — …: PASS | PASS WITH NITS | FAIL — round k/MAX`, the findings table, a recall line
   (`raw R → after verification V → final F`, so lost findings show) and a last dated `verdict: pass|fail` line, which
   is the one the merge gate reads. FAIL when an Important finding stands, a lane is INCOMPLETE, or an untagged lane
   said fail; a lane "fail" with only Nit or Pre-existing rows is PASS WITH NITS. A second opinion from another tool
   goes in with `--extra-line "<one true line>"`: never write a pass for a review that did not run. Exit 3 = the round
   limit (see the top). `--out S/…` instead of `--task` is a dry run.
6. **Report** to the caller: the verdict, the round (k/MAX), the recall line, the findings table, which lanes were
   INCOMPLETE. **Nothing is posted to GitHub**; verdicts stay in this repo. Then `/checkpoint`, and delete the clone
   (`rm -rf S/rv-…`).
