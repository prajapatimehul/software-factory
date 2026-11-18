#!/usr/bin/env python3
"""PreToolUse on Bash: `gh pr merge` needs a passing review on record. Passing tests do not show that every
user-visible surface is still there; that question belongs to a review, and a habit is not a record.

Evidence is a `## Review` block in a file under tasks/ that names the PR (`PR #12` or `owner/repo#12`) and carries
a `verdict: pass` line dated today or yesterday (UTC). The date is on the verdict line or on the block's heading.
The LAST dated verdict for the PR in a file is that file's verdict: a later `fail` blocks, a later `pass` clears.
When the command names the repo (--repo), the block must name that repo, so #12 of one repo never passes for
another. Fails closed on an unparseable payload."""
import datetime
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import CONF, OWNER, ROOT, _conf, file_text, read_payload

MERGE = re.compile(r"\bgh\s+pr\s+merge\b|/pulls/\d+/merge\b")
PRNUM = re.compile(r"\bgh\s+pr\s+merge\s+(?:[^\d\s#][^\s]*\s+)*?#?(\d+)\b|/pulls/(\d+)/merge")
VERDICT = re.compile(r"verdict\W{0,4}(pass|fail)\b(?!\s*\|)", re.I)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def verdicts(num, repo):
    """[(file, verdict, line)] : the last fresh verdict for this PR in each task file."""
    today = datetime.datetime.now(datetime.timezone.utc).date()
    fresh = {str(today), str(today - datetime.timedelta(days=1))}
    ref = re.compile(rf"(?:PR\s*#{num}\b|{re.escape(repo)}#{num}\b)" if repo else rf"(?:PR\s*|[\w.-]+/[\w.-]+)#{num}\b", re.I)
    out, rounds = [], 0
    for path in sorted(glob.glob(os.path.join(ROOT, "tasks", "**", "*.md"), recursive=True)):
        if os.path.basename(path) == "TEMPLATE.md":
            continue
        last = None
        for block in re.split(r"(?m)^(?=## )", file_text(path)):
            if not block.startswith("## Review") or not ref.search(block):
                continue
            head_dates = set(DATE.findall(block.split("\n", 1)[0]))
            for line in block.split("\n"):
                m = VERDICT.search(line)
                if m and (set(DATE.findall(line)) or head_dates) & fresh:
                    rounds += 1
                    last = (os.path.relpath(path, ROOT), m.group(1).lower(), line.strip()[:110])
        if last:
            out.append(last)
    return out, rounds


def main() -> int:
    p = read_payload()
    if p is None:
        print("pr-merge-gate: could not parse the tool payload; refusing.", file=sys.stderr)
        return 2
    cmd = (p.get("tool_input") or {}).get("command", "") or ""
    if p.get("tool_name") != "Bash" or not MERGE.search(cmd):
        return 0
    m = PRNUM.search(cmd)
    num = next((g for g in (m.groups() if m else ()) if g), None)
    if not num:
        print("pr-merge-gate: BLOCKED - could not read the PR number; merge with an explicit number "
              "(`gh pr merge <n> --repo <owner/repo>`).", file=sys.stderr)
        return 2
    rm = re.search(r"(?:--repo|-R)[\s=]+([\w.-]+/[\w.-]+)|repos/([\w.-]+/[\w.-]+)/pulls", cmd)
    repo = next((g for g in (rm.groups() if rm else ()) if g), None)
    found, rounds = verdicts(num, repo)
    fails = [f for f in found if f[1] == "fail"]
    if found and not fails:
        return 0
    name = f"{repo}#{num}" if repo else f"PR #{num}"
    out = [f"pr-merge-gate: BLOCKED - no passing review on record for {name}."]
    for f in fails:
        out.append(f"  latest verdict is FAIL in {f[0]}: {f[2]}")
    limit = _conf.number("MAX_REVIEW_ROUNDS", CONF)
    if fails and rounds >= limit:
        out.append(f"  {rounds} review rounds are on record (MAX_REVIEW_ROUNDS={limit}). Stop the loop and take what "
                   f"keeps failing to {OWNER}.")
    else:
        out.append(f"  Needed: a `## Review` block in the task file that names {name}, written by the reviewer agent "
                   "(never the author), with a `verdict: pass` line dated today or yesterday (UTC). Fix the findings, "
                   "get the review, then merge.")
    print("\n".join(out), file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"pr-merge-gate: internal error {exc!r}; refusing the merge.", file=sys.stderr)
        sys.exit(2)
