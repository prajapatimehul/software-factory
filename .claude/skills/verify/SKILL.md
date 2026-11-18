---
name: verify
description: Run before calling any client work done and before a mail says something works. Code checks first, then the development environment, then production read-only; every check ends PASS, FAIL or NOT SEEN with pasted evidence in the task file. Usage /verify <page|route|job|change> [task-id].
---
# /verify <what> [task-id]

A fork keeps its own map of what to check (URLs, routes, logins and roles, what a pass looks like, production writes to
avoid) in `REGISTRY.md` and, once it grows, in a verify map next to it. Read it first. Never guess a route or a
resource name: copy it from the map or from the code.

## 0. Code checks first (fast, local)

`bash scripts/verify-local.sh <path of the client repo>` runs the repo's own tests, typecheck, lint and build and
writes a record for the commit. Paste its summary line into the task file. A test that also fails on the base branch
is "pre-existing" only after you ran it on the base and pasted that too. Never skip, retry or add a wait to make a
test pass.

## 1. Pick the checks, and write the expected result BEFORE looking

1. List every place the change can show (the task's `## Population`): the thing itself, whatever shares its code,
   and the other view of it (another role, another tenant, another job that reads the same table).
2. For each, write in the task file before looking: what, environment, login and role needed, the expected visible
   result or value, and the writes to avoid.

## 2. Check the login has the role

If the login at hand lacks the role a check needs, the result is NOT SEEN. Never describe a view you did not see and
never infer it from the code. Write which login would be needed. Passwords are never typed into chat or files, and
Claude never types one into a sign-in form: the owner signs in.

## 3. Development first

Use the development environment (a `DEV_MARKERS` target). Writes there are allowed when the check needs them: clean
up what you made and write down what you changed. Before starting, confirm the configuration really points at
development; a copied config file can point at production.

## 4. Production, read only

Only after development passed, and only for what is released. Allowed: reading, filtering, opening a menu. Not
allowed: anything that creates, saves, deletes, sends or switches. If a check needs a production write, stop and ask
the owner; that write needs PROD_CONSENT_TOKEN typed by them.

## 5. Record

One line per check in the task file's `## Evidence`:

```
- YYYY-MM-DD verify <env> <what> as <login> (<role seen>) @ <commit>: PASS|FAIL|NOT SEEN — expected <…>; seen "<pasted text or value>"
```

- PASS needs the pasted text or value that matches the expected one.
- FAIL needs what was seen instead. A fail is fixed, not reworded.
- NOT SEEN needs the reason (role, login, not released, did not load).
- One page, one role, one environment is reported as exactly that, never "works everywhere".
- Something odd that is not the check goes in as a separate "seen" line.

## 6. MAX_REVIEW_ROUNDS rounds, then the owner

A round = fix, re-run the code checks, re-run the check. If the same check still fails after MAX_REVIEW_ROUNDS
rounds, stop. Write what was tried in each round and what is seen now, and bring the owner one short message: the
fail, the tries, your best guess, what you need. Do not start another round on your own.

## 7. Done means

Every check is PASS, or NOT SEEN with a named reason the owner accepts. Then a reviewer grades it, not the author:
`/swarm-review` for a PR, the `work-reviewer` agent for anything else. If the map was wrong, fix it in the same
session from the code, not from memory, and say so in the task file.
