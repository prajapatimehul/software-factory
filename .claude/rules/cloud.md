---
paths:
  - "**/*.sh"
  - "**/*.py"
  - "**/infra/**"
---
# Cloud — two environments, one habit
- Every cloud command names its target with a PROD_MARKERS or DEV_MARKERS string from `factory.conf`. With neither, the hook logs it (`env-explicit=warn` in `.claude/gates.conf`, the shipped mode) or refuses it (`deny`).
- Resource names are often the same in both environments, so a wrong profile looks right. Print the caller identity before any write.
- A production write needs PROD_CONSENT_TOKEN in the command and the owner's own typed consent. Reads are free.
- Empty is not an error and not an answer. The wrong region or account returns an empty list. Run a must-match control before writing "none".
- A resource policy is added to from the live document: read it, merge the statement, write the merged document. Never rewrite one from memory.
- Logs and captures go under the task's folder in `tasks/`, never `/tmp`.
- Times from an SDK are local until converted. Convert to UTC before printing a "Z".
