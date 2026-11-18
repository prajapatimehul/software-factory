#!/usr/bin/env python3
"""The mechanical half of /swarm-review.

  resolve <repo> <pr> [task]         PR facts (head sha, base, files, state) + candidate task files, as JSON
  prepare <repo> <pr> --dir D        a private clone at the PR head, outside the workspace
  review-md --dir D --base B         REVIEW.md from the PR's BASE branch in the clone, never the PR head's copy
  watch   --lane N=path ...          wait for lanes; a lane silent longer than --silence s (default 600) is INCOMPLETE
  write   <repo> <pr> --sha S --lane "N|lens|path" ... (--task F | --out F) [--extra-line "…"] [--clone D]
                                     one '## Review' block per lane, the verdict line, the findings table
  rounds  <repo> <pr> --task F       failing review rounds so far for this PR in F

<repo> is a directory name from CLIENT_REPOS (factory.conf) or owner/repo.

Findings are tagged Important / Nit / Pre-existing and only Important fails. After MAX_REVIEW_ROUNDS failing rounds
in a row, `resolve`, `rounds` and `write` exit 3 and print what keeps failing: the fix loop stops and the owner
decides. One more round runs only with the owner's live REVIEW-ROUNDS-OK consent and `write --owner-ok`.

Nothing is posted to GitHub and nothing is written in the shared checkouts: the clone is `git clone --shared`, so the
checkout is only read. A lane with no verdict line gets a heading ending in INCOMPLETE, which is not a review."""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _conf  # noqa: E402

ROOT = str(_conf.root())
WS = os.path.dirname(ROOT)
CONF = _conf.load()
try:
    MAX_ROUNDS = int(CONF.get("MAX_REVIEW_ROUNDS") or 3)
except ValueError:
    MAX_ROUNDS = 3
OWNER = CONF.get("OWNER_NAME") or "the owner"
# Its own word, not the production token: one yes must not open two doors.
ROUNDS_TOKEN = "REVIEW-ROUNDS-OK"
VERDICT = re.compile(r"^\s*[-*]?\s*\**verdict\**\s*:\s*\**\s*(pass with nits|pass|nits|findings|fail|merge|do-not-merge|do not merge)\b",
                     re.I | re.M)
TAGS = {"important": "Important", "nit": "Nit", "pre-existing": "Pre-existing", "preexisting": "Pre-existing"}
RECALL = re.compile(r"findings\s*:\s*raw\s*(\d+)\s*,\s*after verification\s*(\d+)", re.I)
RANK = {"PASS": 0, "PASS WITH NITS": 1, "FAIL": 2}


def run(cmd, cwd=None, timeout=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def _read(path):
    try:
        return open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return ""


def _inside(path, parent):
    p, q = os.path.realpath(path), os.path.realpath(parent)
    return p == q or p.startswith(q + os.sep)


def repo_dirs():
    return [os.path.normpath(os.path.join(ROOT, os.path.expanduser(r))) for r in (CONF.get("CLIENT_REPOS") or "").split()]


def _full_name(local):
    """owner/repo from the checkout's origin URL, or None."""
    r = run(["git", "-C", local, "remote", "get-url", "origin"]) if os.path.isdir(local) else None
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", r.stdout.strip()) if r and r.returncode == 0 else None
    return m.group(1) if m else None


def repo_of(name):
    """(short, owner/repo, local checkout or None). An owner/repo that is not configured is accepted without a checkout."""
    n = name.strip().rstrip("/")
    for local in repo_dirs():
        short, full = os.path.basename(local), _full_name(local)
        if n in (short, full) or (full and n == full.split("/")[1]):
            return short, full or short, local
    if re.fullmatch(r"[\w.-]+/[\w.-]+", n):
        return n.split("/")[1], n, None
    names = ", ".join(os.path.basename(d) for d in repo_dirs()) or "(CLIENT_REPOS is empty)"
    sys.exit(f"swarm-review: unknown repo {name!r}; one of {names}, or owner/repo")


def find_task(short, full, pr, task=None):
    """Task files naming this PR. Strong: owner/repo#N or '<short> #N'; weak: 'PR #N' in a file naming the repo."""
    files = []
    for d, _, names in os.walk(os.path.join(ROOT, "tasks")):
        files += [os.path.join(d, f) for f in names if f.endswith(".md") and f not in ("TEMPLATE.md", "TASKS.md")]
    if task:
        hit = [f for f in files if os.path.basename(f).startswith(task + "-") or os.path.basename(f) == task + ".md"]
        return [os.path.relpath(f, ROOT) for f in sorted(hit)]
    strong = re.compile(rf"({re.escape(full)}#{pr}\b|{re.escape(short)}\s*#{pr}\b|{re.escape(short)}\s+PR\s*#{pr}\b)", re.I)
    weak = re.compile(rf"\bPR\s*#{pr}\b")
    repo_word = re.compile(re.escape(short), re.I)
    scored = []
    for f in files:
        text = _read(f)
        s = len(strong.findall(text)) * 3 + (len(weak.findall(text)) if repo_word.search(text) else 0)
        if s:
            scored.append((s, os.path.relpath(f, ROOT)))
    return [p for _, p in sorted(scored, key=lambda x: (-x[0], x[1]))]


# --- rounds ----------------------------------------------------------------

def _placeholder_row(ln):
    """'| 2 | - | - | no findings reported | - |' is a lane's 'nothing here' row, not a finding."""
    cells = [c.strip() for c in ln.strip().strip("|").split("|")][1:]
    real = [c for c in cells if c not in ("", "-", "—", "–")]
    return len(real) <= 1 and bool(re.match(r"^(none|no findings?\b)", real[0] if real else "none", re.I))


def _table_row(ln):
    return (ln.startswith("|") and not re.match(r"^\|[\s:|-]+\|?$", ln)
            and not re.match(r"^\|\s*(lane\s*\|)?\s*(severity|tag)\b", ln, re.I))


def count_rounds(text, repo, pr):
    """One '### Swarm verdict' line for repo#pr = one round. failing_streak = FAIL rounds since the last PASS or
    PASS WITH NITS; rows = the findings rows of those failing rounds (what keeps failing)."""
    ref = re.compile(rf"{re.escape(repo)}#{pr}\b")
    rounds, streak, rows, cur = 0, 0, [], None
    for ln in text.splitlines():
        if ln.startswith("### Swarm verdict") and ref.search(ln):
            rounds += 1
            m = re.search(r":\s*(PASS WITH NITS|PASS|FAIL)\b", ln)
            if m and m.group(1) == "FAIL":
                streak += 1
                cur = []
                rows.append((ln, cur))
            else:
                streak, rows, cur = 0, [], None
            continue
        if cur is not None:
            if _table_row(ln) and not _placeholder_row(ln):
                cur.append(ln)
            elif not ln.startswith("|"):
                cur = None
    return {"rounds": rounds, "failing_streak": streak,
            "rows": [r for _, rs in rows for r in rs], "headings": [h for h, _ in rows]}


def stop_message(repo, pr, target, cr):
    rows = cr["rows"] or ["(no findings rows; the rounds failed on INCOMPLETE lanes or untagged verdicts)"]
    return (f"swarm-review: STOP — {repo}#{pr} has failed {cr['failing_streak']} review rounds in {target}; round "
            f"{cr['failing_streak'] + 1} is refused (limit {MAX_ROUNDS}). Stop the fix loop and bring {OWNER} this summary "
            "of what keeps failing:\n  " + "\n  ".join(cr["headings"]) + "\n  findings:\n  " + "\n  ".join(rows)
            + f"\n  {OWNER} decides: change the approach, split the PR, accept the findings, or allow one more round "
            f"(their live {ROUNDS_TOKEN} consent + `write --owner-ok`).")


def rounds_consent():
    # Next to this file, not under ROOT: the hooks are code, and FACTORY_ROOT only moves the data.
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude", "hooks"))
    try:
        import _consent
        return bool(_consent.live(ROUNDS_TOKEN))
    except Exception:
        return False  # no helper, or it does not know the token: the extra round stays refused


# --- resolve / prepare -----------------------------------------------------

def cmd_resolve(a):
    short, full, local = repo_of(a.repo)
    r = run(["gh", "pr", "view", str(a.pr), "--repo", full, "--json",
             "number,title,state,mergedAt,headRefOid,headRefName,baseRefName,baseRefOid,url,files"])
    if r.returncode:
        sys.exit(f"swarm-review: gh pr view failed: {r.stderr.strip()}")
    pr = json.loads(r.stdout)
    out = {"repo": full, "short": short, "local": local, "pr": pr["number"], "title": pr["title"], "state": pr["state"],
           "mergedAt": pr["mergedAt"], "head": pr["headRefOid"], "headRef": pr["headRefName"], "base": pr["baseRefName"],
           "baseOid": pr["baseRefOid"], "url": pr["url"], "files": [f["path"] for f in pr["files"]],
           "tasks": find_task(short, full, a.pr, a.task)}
    counted = {t: count_rounds(_read(os.path.join(ROOT, t)), full, a.pr) for t in out["tasks"]}
    out["failing_rounds"] = {t: c["failing_streak"] for t, c in counted.items()}
    out["limit"] = MAX_ROUNDS
    print(json.dumps(out, indent=1))
    # Stop before any lane runs: the named task, or any candidate whose verdict lines name this PR.
    for t in (out["tasks"][:1] if a.task else out["tasks"]):
        if counted[t]["failing_streak"] >= MAX_ROUNDS:
            print(stop_message(full, a.pr, t, counted[t]), file=sys.stderr)
            return 3
    return 0


def base_review_md(clone, base):
    """(text or None, note). A PR that edits REVIEW.md must not change the rules it is reviewed by."""
    ref = f"gh/{base}"
    r = run(["git", "-C", clone, "show", f"{ref}:REVIEW.md"])
    if r.returncode:
        return None, f"no REVIEW.md on base {ref} (lanes review without a repo review contract)"
    note = f"REVIEW.md from base {ref} ({len(r.stdout.splitlines())} lines)"
    head = run(["git", "-C", clone, "show", "HEAD:REVIEW.md"])
    if head.returncode or head.stdout != r.stdout:
        note += "; the PR changes REVIEW.md — lanes use the base copy, and the change itself is a finding to review"
    return r.stdout, note


def cmd_review_md(a):
    text, note = base_review_md(a.dir, a.base)
    print(note)
    if text is not None:
        print(text, end="")
    return 0


def _link_deps(clone, local):
    """node_modules: symlink from a checkout or worktree whose package-lock.json is byte-identical, else say so."""
    lock = os.path.join(clone, "package-lock.json")
    if not os.path.exists(lock):
        return None
    donors = [local] + [ln.split(" ", 1)[1] for ln in run(["git", "-C", local, "worktree", "list", "--porcelain"]).stdout.splitlines()
                        if ln.startswith("worktree ")]
    want = open(lock, "rb").read()
    for d in donors:
        nm, dl = os.path.join(d, "node_modules"), os.path.join(d, "package-lock.json")
        if os.path.isdir(nm) and os.path.exists(dl) and open(dl, "rb").read() == want:
            os.symlink(nm, os.path.join(clone, "node_modules"))
            return f"node_modules -> {nm} (package-lock.json identical)"
    return "node_modules NOT provided: no checkout with an identical package-lock.json; the tests lane runs `npm ci` in the clone"


def cmd_prepare(a):
    short, full, local = repo_of(a.repo)
    if not local or not os.path.isdir(os.path.join(local, ".git")) and not os.path.isfile(os.path.join(local, ".git")):
        sys.exit(f"swarm-review: no local checkout for {a.repo}; add it to CLIENT_REPOS in factory.conf")
    d = os.path.abspath(a.dir)
    if _inside(d, WS) or any(_inside(d, r) for r in repo_dirs()):
        sys.exit(f"swarm-review: refusing {d}: the clone goes in a scratch directory, never in the workspace")
    if os.path.exists(d):
        sys.exit(f"swarm-review: {d} exists; pick a fresh directory")
    sha, base = a.sha, a.base
    if not (sha and base):
        r = run(["gh", "pr", "view", str(a.pr), "--repo", full, "--json", "headRefOid,baseRefName"])
        if r.returncode:
            sys.exit(f"swarm-review: gh pr view failed: {r.stderr.strip()}")
        info = json.loads(r.stdout)
        sha, base = sha or info["headRefOid"], base or info["baseRefName"]
    origin = run(["git", "-C", local, "remote", "get-url", "origin"]).stdout.strip()
    if not origin:
        sys.exit(f"swarm-review: {local} has no origin remote")
    for c in (["git", "clone", "--quiet", "--shared", "--no-checkout", local, d],
              ["git", "-C", d, "fetch", "--quiet", origin, f"pull/{a.pr}/head", "+refs/heads/*:refs/remotes/gh/*"],
              ["git", "-C", d, "-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", sha]):
        r = run(c, timeout=600)
        if r.returncode:
            sys.exit(f"swarm-review: {' '.join(c[:4])} failed: {r.stderr.strip()}")
    head = run(["git", "-C", d, "rev-parse", "HEAD"]).stdout.strip()
    if head != sha:
        sys.exit(f"swarm-review: clone HEAD {head} != PR head {sha}")
    steps = [f"clone {d} HEAD {head}"]
    rv, note = base_review_md(d, base)
    if rv is not None:
        with open(d + ".REVIEW-base.md", "w", encoding="utf-8") as f:
            f.write(rv)
        note += f" -> {d}.REVIEW-base.md (give this path to every lane)"
    steps.append(note)
    deps = _link_deps(d, local)
    if deps:
        steps.append(deps)
    st = run(["git", "-C", d, "status", "--porcelain", "--untracked-files=no"]).stdout.strip()
    steps.append(f"git status (tracked) at prepare: {'clean' if not st else st}")
    print("\n".join(steps))
    return 0


# --- lanes -----------------------------------------------------------------

def lane_status(path, silence, now=None):
    now = now or time.time()
    if not path or not os.path.exists(path):
        return "waiting", None
    text = _read(path)
    if VERDICT.search(text) or '"type":"result"' in text.replace(" ", ""):
        return "done", None
    idle = now - os.path.getmtime(path)
    return ("incomplete" if idle > silence else "running"), int(idle)


def cmd_watch(a):
    lanes = dict(x.split("=", 1) for x in a.lane)
    start = time.time()
    while True:
        st = {n: lane_status(p, a.silence) for n, p in lanes.items()}
        for n in lanes:  # a lane that never wrote anything is silent since the watch started
            if st[n][0] == "waiting" and time.time() - start > a.silence:
                st[n] = ("incomplete", int(time.time() - start))
        if all(s in ("done", "incomplete") for s, _ in st.values()) or a.once:
            print(json.dumps({n: {"status": s, "silent_s": i} for n, (s, i) in st.items()}))
            return 0
        time.sleep(a.poll)


def _lane_text(path):
    text = _read(path)
    if text.lstrip().startswith("{"):  # a headless run saved as stream-json: take the final result
        for ln in reversed(text.splitlines()):
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            if isinstance(o, dict) and o.get("type") == "result":
                return o.get("result") or ""
    return text


def _norm(v):
    v = v.lower().replace("do not merge", "do-not-merge")
    return {"pass": "PASS", "merge": "PASS", "nits": "PASS WITH NITS", "pass with nits": "PASS WITH NITS",
            "fail": "FAIL", "do-not-merge": "FAIL", "findings": "FAIL"}[v]


def _tag(row):
    cells = [c.strip().strip("*").lower() for c in row.strip().strip("|").split("|")]
    return TAGS.get(cells[0]) if cells else None


def build(repo, pr, sha, date, lanes, extra_line="", silence_min=10, round_no=None):
    """(markdown, final verdict) for one review round. lanes = [(n, lens, output path)]."""
    ref = f"{repo}#{pr} at {sha[:7]}"
    out, verdicts, rows, incomplete = [], [], [], []
    tags = {"Important": 0, "Nit": 0, "Pre-existing": 0, None: 0}
    raw = verified = 0
    unreported, downgraded = [], []
    for n, lens, path in lanes:
        text = _lane_text(path) if path and os.path.exists(path) else ""
        found = VERDICT.findall(text)
        v = None
        if not found:
            incomplete.append(n)
            out.append(f"## Review — {date} {ref} — reviewer {n} ({lens}) — INCOMPLETE")
            if not text.strip():
                out += [f"- lane silent > {silence_min} min ({path or 'no output file'}); not a review.", ""]
                continue
            # The lane wrote something but no verdict line: keep its text and its rows, never drop them.
            out.append(f"- lane ended without a verdict line ({path}); its text is kept below and its rows are in the "
                       "table, but it is not a review.")
        else:
            # The worst verdict the lane wrote wins: 'verdict: fail' then 'verdict: nits' is still FAIL.
            v = max((_norm(x) for x in found), key=RANK.get)
            out.append(f"## Review — {date} {ref} — reviewer {n} ({lens})")
        lane_rows = []
        for ln in text.strip().splitlines():
            if ln.startswith("#"):  # a lane's own headings must never become a '## Review' line
                ln = "#### " + ln.lstrip("#").strip()
            elif _table_row(ln) and not _placeholder_row("| x " + ln):
                lane_rows.append(ln)
                rows.append(f"| {n} " + ln)
            out.append(ln)
        out.append("")
        lane_tags = [_tag(r) for r in lane_rows]
        for t in lane_tags:
            tags[t] += 1
        m = RECALL.findall(text)
        if m:
            raw += int(m[-1][0])
            verified += int(m[-1][1])
        else:
            unreported.append(n)
        if v:
            # Only an Important finding fails. A lane 'fail' whose rows are all tagged and none Important is a pass
            # with nits; an untagged row keeps the lane's own verdict; an Important row fails even under a lane 'pass'.
            if "Important" in lane_tags:
                v = "FAIL"
            elif v == "FAIL" and lane_rows and None not in lane_tags:
                v = "PASS WITH NITS"
                downgraded.append(n)
            elif v == "PASS" and lane_rows and None not in lane_tags:
                v = "PASS WITH NITS"
            verdicts.append(v)
    if extra_line.strip():
        out.append(extra_line.strip())
    final = "FAIL" if ("FAIL" in verdicts or incomplete or not verdicts) else (
        "PASS WITH NITS" if "PASS WITH NITS" in verdicts else "PASS")
    why = []
    if incomplete:
        why.append(f"lane(s) {', '.join(incomplete)} INCOMPLETE (silent or no verdict line) — rerun them")
    if "FAIL" in verdicts:
        why.append(f"{tags['Important']} Important finding(s)" if tags["Important"] else "a lane failed")
    if downgraded:
        why.append(f"lane(s) {', '.join(downgraded)} said fail with only Nit / Pre-existing rows: not a fail")
    rnd = f" — round {round_no}/{MAX_ROUNDS}" if round_no else ""
    # The round marker goes after the verdict word: readers parse '<ref> at <sha7>: VERDICT'.
    out += ["", f"### Swarm verdict — {date} {ref}: {final}{rnd}" + (f" ({'; '.join(why)})" if why else ""),
            "| lane | tag | where | finding | cmd → output |", "|---|---|---|---|---|"]
    out += rows or ["| – | – | – | no findings reported | – |"]
    rec = (f"- recall: raw {raw} → after verification {verified} → final {len(rows)} (Important {tags['Important']}, "
           f"Nit {tags['Nit']}, Pre-existing {tags['Pre-existing']}, untagged {tags[None]})")
    if unreported:
        rec += f"; raw/verified counts not reported by lane(s) {', '.join(unreported)}, so those sums are partial"
    out.append(rec)
    # One plain dated line last: the merge gate reads the last 'verdict: pass|fail' of the file, and a lane's own
    # verdict line must not be that line.
    out.append(f"- {date} verdict: {'fail' if final == 'FAIL' else 'pass'} — swarm of {len(lanes)} lane(s) on {ref}: {final}")
    return "\n".join(out) + "\n", final


def cmd_write(a):
    _, full, _ = repo_of(a.repo)
    lanes = [tuple((x.split("|", 2) + ["", ""])[:3]) for x in a.lane]
    date = a.date or str(datetime.datetime.now(datetime.timezone.utc).date())
    target = a.task or a.out
    if not target:
        sys.exit("swarm-review: --task or --out is required")
    if a.task and not _inside(os.path.abspath(a.task), os.path.join(ROOT, "tasks")):
        sys.exit("swarm-review: --task must be a file under tasks/ (verdicts stay in this repo)")
    cr = count_rounds(_read(target), full, a.pr)
    if cr["failing_streak"] >= MAX_ROUNDS and not (a.owner_ok and rounds_consent()):
        print(stop_message(full, a.pr, target, cr), file=sys.stderr)
        return 3
    text, final = build(full, a.pr, a.sha, date, lanes, a.extra_line or "", round_no=cr["failing_streak"] + 1)
    if a.clone:
        st = run(["git", "-C", a.clone, "status", "--porcelain", "--untracked-files=no"]).stdout.strip()
        text += f"- clone {a.clone}: tracked files {'unchanged' if not st else 'CHANGED by a lane: ' + st[:200]}\n"
    with open(target, "a", encoding="utf-8") as f:
        f.write("\n" + text)
    print(f"{final} — round {cr['failing_streak'] + 1}/{MAX_ROUNDS} — written to {target}")
    return 0


def cmd_rounds(a):
    _, full, _ = repo_of(a.repo)
    cr = count_rounds(_read(a.task), full, a.pr)
    print(json.dumps({"rounds": cr["rounds"], "failing_streak": cr["failing_streak"], "limit": MAX_ROUNDS}))
    if cr["failing_streak"] >= MAX_ROUNDS:
        print(stop_message(full, a.pr, a.task, cr), file=sys.stderr)
        return 3
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    r = s.add_parser("resolve"); r.add_argument("repo"); r.add_argument("pr", type=int); r.add_argument("task", nargs="?")
    r = s.add_parser("prepare"); r.add_argument("repo"); r.add_argument("pr", type=int); r.add_argument("--dir", required=True)
    r.add_argument("--sha"); r.add_argument("--base", help="the PR's base branch (default: from gh pr view)")
    r = s.add_parser("review-md"); r.add_argument("--dir", required=True); r.add_argument("--base", required=True)
    r = s.add_parser("watch"); r.add_argument("--lane", action="append", required=True)
    r.add_argument("--silence", type=int, default=600); r.add_argument("--poll", type=int, default=30)
    r.add_argument("--once", action="store_true")
    r = s.add_parser("write"); r.add_argument("repo"); r.add_argument("pr", type=int); r.add_argument("--sha", required=True)
    r.add_argument("--lane", action="append", required=True); r.add_argument("--extra-line")
    r.add_argument("--task"); r.add_argument("--out"); r.add_argument("--date"); r.add_argument("--clone")
    r.add_argument("--owner-ok", action="store_true", help=f"a round past the limit; counts only with a live {ROUNDS_TOKEN} consent")
    r = s.add_parser("rounds"); r.add_argument("repo"); r.add_argument("pr", type=int); r.add_argument("--task", required=True)
    a = p.parse_args(argv)
    return {"resolve": cmd_resolve, "prepare": cmd_prepare, "review-md": cmd_review_md, "watch": cmd_watch,
            "write": cmd_write, "rounds": cmd_rounds}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
