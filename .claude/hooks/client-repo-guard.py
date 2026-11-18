#!/usr/bin/env python3
"""PreToolUse (Write|Edit|NotebookEdit|Bash): nothing from this private repo is written into a client repo.

CLIENT_REPOS belong to the client; anything written there is effectively published. This hook reads the tool's
own payload, so it blocks before the bytes land.

Covers: file writes into a client repo or one of its git worktrees; `cat > file <<EOF` / tee / echo redirects;
commit, tag and merge messages; `gh pr|issue|release` titles and bodies for a client repo.
Private content: this repo's file names and ids (MISTAKE.md, STATE.md, ledger files, task ids, "mistake 12"),
this repo's own directory name, PRIVATE_WORDS from factory.conf, and the owner's name on a line about who said
or got something wrong. Fails closed on an unparseable payload."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _lib import CONF, ROOT, _conf

REPOS = [str(r) for r in _conf.repos(CONF)]
_own = os.path.basename(ROOT)
_extra = [re.escape(w) for w in _conf.words("PRIVATE_WORDS", CONF)]
if len(_own) >= 5 and _own not in [os.path.basename(r) for r in REPOS]:
    _extra.append(re.escape(_own))
PRIVATE = re.compile(
    r"(?<![\w-])(?:mistake\s*#?\d+|learning\s*#?\d+|MISTAKE\.md|LEARNING\.md|STATE(?:-LOG)?\.md|RULES\.md|factory\.conf"
    r"|(?:asks|promises|claims|mail|mistakes|triggers)\.tsv|T-\d{3}" + "".join("|" + w for w in _extra) + r")(?![\w-])", re.I)
_owner = (CONF.get("OWNER_NAME") or "").strip()
OWNER_LINE = re.compile(r"\b" + re.escape(_owner) + r"\b.*\b(said|told|asked|promised|wrong|mistake|forgot)\b"
                        r"|\b(said|told|asked|promised|wrong|mistake|forgot)\b.*\b" + re.escape(_owner) + r"\b", re.I) \
    if len(_owner) >= 3 and _owner.lower() != "owner" else None
QUOTED = r"(?:'([^']*)'|\"([^\"]*)\"|(\S+))"


def git_main_checkout(path):
    """The main checkout a path belongs to, following a worktree's .git file. '' when not in a repo."""
    d = path
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    while d:
        g = os.path.join(d, ".git")
        if os.path.isdir(g):
            return d
        if os.path.isfile(g):   # a worktree: "gitdir: <main>/.git/worktrees/<name>"
            m = re.search(r"gitdir:\s*(.+?)/\.git/worktrees/", open(g).read())
            return os.path.realpath(os.path.join(d, m.group(1))) if m else d
        if os.path.dirname(d) == d:
            return ""
        d = os.path.dirname(d)
    return ""


def is_client_path(path, base=""):
    p = os.path.expanduser(path)
    if not os.path.isabs(p):
        p = os.path.join(base or os.getcwd(), p)
    p = os.path.realpath(p)
    inside = lambda x: any(x == r or x.startswith(r + os.sep) for r in REPOS)
    return inside(p) or inside(git_main_checkout(p))


def cd_base(cmd, cwd):
    """Where a relative path in a Bash command lands: the payload cwd, moved by each `cd X`."""
    base = cwd or os.getcwd()
    for m in re.finditer(r"(?:^|[;&|(\n])\s*cd\s+" + QUOTED, cmd):
        target = os.path.expanduser(m.group(1) or m.group(2) or m.group(3))
        base = target if os.path.isabs(target) else os.path.join(base, target)
    return base


def read_files(pattern, text):
    out = []
    for m in re.finditer(pattern + r"[= ]\s*" + QUOTED, text):
        f = m.group(1) or m.group(2) or m.group(3)
        if f != "-":
            try:
                out.append(open(os.path.expanduser(f)).read())
            except OSError:
                out.append("")
    return out


def bash_writes(cmd, base):
    """[(target path, text)] for what a Bash command would publish."""
    out = []
    gh = re.search(r"\bgh\s+(?:pr|issue|release)\s+(?:create|edit|comment|merge|review)\b", cmd)
    if gh:
        repo = re.search(r"(?:-R|--repo)[= ]\s*['\"]?([\w./:-]+)", cmd)
        names = [os.path.basename(r) for r in REPOS]
        target = base
        if repo and repo.group(1).rstrip("/").rsplit("/", 1)[-1] in names:
            target = REPOS[names.index(repo.group(1).rstrip("/").rsplit("/", 1)[-1])]
        texts = read_files(r"(?:--body-file|--notes-file|(?<![\w-])-F)", cmd)
        texts += [m.group(1) or m.group(2) or m.group(3) or "" for m in
                  re.finditer(r"(?:--body|--title|--subject|--notes|(?<![\w-])-[btn])[= ]\s*" + QUOTED, cmd)]
        heredoc = re.search(r"<<-?\s*['\"]?(\w+)['\"]?\n(.*?)\n\s*\1\b", cmd, re.S)
        out.append((os.path.join(target, ".gh-text"), "\n".join(texts + ([heredoc.group(2)] if heredoc else []))))
    gc = re.search(r"\bgit\s+((?:-C\s+" + QUOTED + r"\s+|--?[A-Za-z][\w-]*(?:=\S+)?\s+)*)(?:commit|tag|merge|notes)\b", cmd)
    if gc:
        d = re.search(r"-C\s+" + QUOTED, gc.group(1))
        repo_dir = os.path.expanduser((d.group(1) or d.group(2) or d.group(3)) if d else "")
        rest = cmd[gc.end():]
        out.append((os.path.join(base, repo_dir, ".git-message"), "\n".join(read_files(r"(?:-F|--file)", rest) + [rest])))
    m = re.search(r"(?:cat|tee)\s*(?:-a\s*)?>*\s*([^\s|;&<>]+)[^\n]*<<-?\s*['\"]?(\w+)", cmd)
    if m:
        out.append((m.group(1), cmd.split(m.group(0), 1)[-1]))
    for m in re.finditer(r">>?\s*([^\s|;&<>]+)", cmd):
        if re.search(r"\b(echo|printf)\b", cmd):
            out.append((m.group(1), cmd))
    return out


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        # A guard that passes on input it cannot read is a guard that can be switched off by accident.
        print(f"client-repo-guard: could not parse the tool payload ({exc}); refusing.", file=sys.stderr)
        return 2
    if not REPOS:
        return 0
    name, ti, cwd = payload.get("tool_name", ""), payload.get("tool_input") or {}, payload.get("cwd", "") or ""
    if name == "Bash":
        base = cd_base(ti.get("command", "") or "", cwd)
        writes = bash_writes(ti.get("command", "") or "", base)
    elif name in ("Write", "Edit", "NotebookEdit", "MultiEdit"):
        base = cwd
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        writes = [(path, str(ti.get("content") or ti.get("new_string") or ti.get("new_source") or ""))]
    else:
        return 0
    for path, text in writes:
        if not path or not text or not is_client_path(path, base):
            continue
        hits = []
        for ln in text.split("\n"):
            m = PRIVATE.search(ln) or (OWNER_LINE.search(ln) if OWNER_LINE else None)
            if m:
                hits.append((m.group(0)[:40], ln.strip()[:90]))
        if hits:
            out = [f"client-repo-guard: BLOCKED - {path} is in a repo the client can read, and this write carries private content.",
                   "A client repo gets the technical fact and the command that proves it. Never where it was recorded,",
                   "what went wrong on the way, or the name of a private file."]
            out += [f"  {tok!r} in: {ln}" for tok, ln in hits[:6]]
            print("\n".join(out), file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
