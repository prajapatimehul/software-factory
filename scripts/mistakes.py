#!/usr/bin/env python3
"""The mistake store. Stories live in learning/MISTAKE.md (append-only, read one entry at a time); the table
learning/mistakes.tsv carries one row per entry; the counts in RULES.md are written by this script, never by hand.
A new number is the highest heading number + 1, never the heading count + 1 (numbers can have gaps).

  mistakes.py next                      the number the next entry gets
  mistakes.py show N                    every entry numbered N
  mistakes.py counts [--write]          shape<TAB>primary<TAB>involved; --write rewrites the counts block in RULES.md
  mistakes.py check                     exit 2 when RULES.md disagrees with the table, a heading has no row, or a row
                                        points at the wrong line; prints OWED: shapes with 2 or more prose-only rows
  mistakes.py relink                    rewrite the line column from the headings (after an edit above an entry)
  mistakes.py new --shape P5 --caught-by … --reached … --actor … --summary "…"
                  (--trigger RE | --mechanism NAME | --prose-only) [--involved "P1, P3"] [--rule "…"]
                                        appends the entry skeleton and the row, prints the number

FACTORY_ROOT points the script at another checkout (the tests use it)."""
import argparse
import csv
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _conf  # noqa: E402

ROOT = str(_conf.root())
MD, TSV, RULES = (os.path.join(ROOT, p) for p in ("learning/MISTAKE.md", "learning/mistakes.tsv", "RULES.md"))
FIELDS = ["id", "line", "date", "primary", "involved", "caught_by", "reached", "actor", "trigger", "rule", "mechanism",
          "proposed", "summary", "inferred"]
HEADING = re.compile(r"^## (\d+)(?:[.\s—–-]|$)")
BEGIN, END = "<!-- counts:begin -->", "<!-- counts:end -->"
CAUGHT = ("self-same-output", "self-later", "reviewer-agent", "subagent", "control-query", "hook-or-script", "owner",
          "client", "unknown")
REACHED = ("nobody", "file", "owner", "client-draft", "client-sent", "prod", "public", "unknown")
ACTORS = ("main", "subagent", "reviewer-agent", "script", "unknown")


def headings():
    out = []
    if not os.path.exists(MD):
        return out
    with open(MD) as f:
        for i, line in enumerate(f, 1):
            m = HEADING.match(line)
            if m:
                out.append((int(m.group(1)), i, line.rstrip("\n")))
    return out


def rows():
    with open(TSV, newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        return list(r), (r.fieldnames or FIELDS)


def shapes_in(cell):
    return [s for s in re.split(r"[,\s]+", (cell or "").strip()) if s]


def counts():
    rs, _ = rows()
    primary, involved = {}, {}
    for r in rs:
        p = (r["primary"] or "").strip()
        if p:
            primary[p] = primary.get(p, 0) + 1
            involved[p] = involved.get(p, 0) + 1
        for s in shapes_in(r["involved"]):
            if s != p:
                involved[s] = involved.get(s, 0) + 1
    key = lambda s: (int(re.sub(r"\D", "", s) or 0), s)  # noqa: E731
    return {s: (primary.get(s, 0), involved.get(s, 0)) for s in sorted(set(primary) | set(involved), key=key)}


def card_rows(text):
    """(shape, 'p / i', line_index) for every table row inside the counts block."""
    lines = text.split("\n")
    try:
        a, b = lines.index(BEGIN), lines.index(END)
    except ValueError:
        return lines, None, None, []
    found = []
    for i in range(a + 1, b):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")] if lines[i].startswith("| P") else []
        if len(cells) >= 2 and re.fullmatch(r"P\d+", cells[0]):
            found.append((cells[0], cells[-1], i))
    return lines, a, b, found


def write_counts():
    c = counts()
    lines, a, b, found = card_rows(open(RULES).read())
    if a is None:
        sys.exit(f"RULES.md has no {BEGIN} … {END} block")
    seen = set()
    for shape, _, i in found:
        p, inv = c.get(shape, (0, 0))
        lines[i] = re.sub(r"\| [^|]+ \|\s*$", f"| {p} / {inv} |", lines[i])
        seen.add(shape)
    # A shape used in the table but missing from the card gets a bare row, so the count is never lost.
    lines[b:b] = [f"| {s} | {p} / {inv} |" for s, (p, inv) in c.items() if s not in seen]
    with open(RULES, "w") as f:
        f.write("\n".join(lines))


def check():
    problems, c = [], counts()
    _, a, _, found = card_rows(open(RULES).read())
    if a is None:
        problems.append(f"RULES.md has no {BEGIN} block")
    card = {s: v for s, v, _ in found}
    for s, (p, inv) in c.items():
        if card.get(s) != f"{p} / {inv}":
            problems.append(f"RULES.md says {s} {card.get(s, '(missing)')}; the table says {p} / {inv}")
    for s, v in card.items():
        if s not in c and v != "0 / 0":
            problems.append(f"RULES.md says {s} {v}; the table has no row for it")
    rs, _ = rows()
    by_line = {(int(r["line"]), r["id"]) for r in rs if (r["line"] or "").strip()}
    hs = headings()
    for n, line, text in hs:
        if (line, str(n)) not in by_line:
            problems.append(f"no row for heading {n} (line {line}): {text[:70]}")
    hl = {(line, str(n)) for n, line, _ in hs}
    for r in rs:
        if (r["line"] or "").strip() and (int(r["line"]), r["id"]) not in hl:
            problems.append(f"row {r['id']} points at line {r['line']}, which is not its heading — run: mistakes.py relink")
    trig = os.path.join(ROOT, "learning/triggers.tsv")
    if os.path.exists(trig):
        with open(trig, newline="") as f:
            for t in csv.DictReader(f, delimiter="\t"):
                try:
                    re.compile(t.get("regex") or "")
                except re.error as e:
                    problems.append(f"triggers.tsv {t.get('id')}: bad regex ({e})")
    prose = {}
    for r in rs:
        if (r["mechanism"] or "").strip() == "prose" and (r["primary"] or "").strip():
            prose[r["primary"]] = prose.get(r["primary"], 0) + 1
    owed = [f"{s} ({n} prose-only)" for s, n in sorted(prose.items()) if n >= 2]
    for p in problems:
        print(p)
    if owed:
        print("OWED (a shape with 2 or more prose-only entries needs a mechanism: a trigger row or a hook): " + ", ".join(owed))
    if not problems:
        print(f"mistakes: {len(hs)} entries, table and RULES.md agree")
    sys.exit(2 if problems else 0)


def relink():
    rs, fields = rows()
    hs = headings()
    if [r["id"] for r in rs] != [str(n) for n, _, _ in hs]:
        sys.exit(f"row ids and heading numbers differ in order: {len(rs)} rows vs {len(hs)} headings — fix by hand")
    for r, (_, line, _) in zip(rs, hs):
        r["line"] = str(line)
    with open(TSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rs)
    print(f"relinked {len(rs)} rows")


def show(n):
    lines = open(MD).read().split("\n")
    starts = [i for i, l in enumerate(lines) if HEADING.match(l)]
    hits = [i for i in starts if int(HEADING.match(lines[i]).group(1)) == n]
    if not hits:
        sys.exit(f"no entry numbered {n}")
    for i in hits:
        nxt = next((j for j in starts if j > i), len(lines))
        print("\n".join(lines[i:nxt]).rstrip() + "\n")


def refuse(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def new(a):
    if not (a.trigger or a.mechanism or a.prose_only):
        refuse("refused: an entry ships a --trigger (regex the hooks match) or a --mechanism (hook/script name), "
               "or is marked --prose-only (counted as debt)")
    if not re.fullmatch(r"P\d+", a.shape):
        refuse("--shape must look like P5")
    for v, ok, name in ((a.caught_by, CAUGHT, "--caught-by"), (a.reached, REACHED, "--reached"), (a.actor, ACTORS, "--actor")):
        if v not in ok:
            refuse(f"{name} must be one of {', '.join(ok)}")
    if a.trigger:
        try:
            re.compile(a.trigger)
        except re.error as e:
            refuse(f"--trigger is not a valid regex ({e})")
    n = max((h[0] for h in headings()), default=0) + 1
    now = datetime.datetime.now(datetime.timezone.utc)
    inv = f", {a.involved} involved" if a.involved else ""
    mech = a.mechanism or ("trigger: `" + a.trigger + "`" if a.trigger else "prose only")
    body = (f"\n## {n} — {a.summary} ({now:%Y-%m-%d}; recorded {now:%H:%M:%SZ})\n\n**What happened.** \n\n**What was true.** \n\n"
            f"**Why.** \n\n**Cost.** \n\n**Rule.** {a.rule or ''} Shape: **{a.shape} primary**{inv}. Mechanism: {mech}.\n")
    # Start on a fresh line even when the file does not end with one, or the heading would not be a heading.
    if os.path.exists(MD) and os.path.getsize(MD) and not open(MD).read().endswith("\n"):
        body = "\n" + body
    with open(MD, "a") as f:
        f.write(body)
    line = [l for num, l, _ in headings() if num == n][-1]
    _, fields = rows()
    row = {"id": n, "line": line, "date": f"{now:%Y-%m-%d}", "primary": a.shape, "involved": a.involved or "",
           "caught_by": a.caught_by, "reached": a.reached, "actor": a.actor, "trigger": a.trigger or "", "rule": a.rule or "",
           "mechanism": a.mechanism or ("trigger" if a.trigger else "prose"), "proposed": "", "summary": a.summary, "inferred": ""}
    tail = open(TSV).read()
    with open(TSV, "a") as f:
        if tail and not tail.endswith("\n"):
            f.write("\n")
        f.write("\t".join(str(row.get(h, "")).replace("\t", " ").replace("\n", " ") for h in fields) + "\n")
    print(n)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("next")
    sub.add_parser("check")
    sub.add_parser("relink")
    sub.add_parser("show").add_argument("n", type=int)
    sub.add_parser("counts").add_argument("--write", action="store_true")
    p = sub.add_parser("new")
    for flag in ("--shape", "--caught-by", "--reached", "--actor", "--summary"):
        p.add_argument(flag, required=True)
    p.add_argument("--involved", default="")
    p.add_argument("--trigger")
    p.add_argument("--mechanism")
    p.add_argument("--rule")
    p.add_argument("--prose-only", action="store_true")
    a = ap.parse_args()
    if a.cmd == "next":
        print(max((h[0] for h in headings()), default=0) + 1)
    elif a.cmd == "show":
        show(a.n)
    elif a.cmd == "counts":
        if a.write:
            write_counts()
        else:
            for s, (p, i) in counts().items():
                print(f"{s}\t{p}\t{i}")
    elif a.cmd == "check":
        check()
    elif a.cmd == "relink":
        relink()
    elif a.cmd == "new":
        new(a)


if __name__ == "__main__":
    main()
