import json
import os
import unittest

from _fixture import make_root, read, run, write

REPO = "acme/app"   # an owner/repo that is not in CLIENT_REPOS: accepted without a checkout
FAIL_LANE = """Checked the three claims.
findings: raw 4, after verification 2
| tag | where | finding | cmd → output |
|---|---|---|---|
| Important | src/export.py:40 | the archive path drops the tenant id | `pytest -k tenant` → 1 failed |
| Nit | src/export.py:12 | unused import | `ruff check` → F401 |
verdict: fail
"""
NIT_LANE = """findings: raw 2, after verification 1
| tag | where | finding | cmd → output |
|---|---|---|---|
| Nit | README.md:3 | typo | read |
verdict: fail
"""
PRE_LANE = """findings: raw 1, after verification 1
| tag | where | finding | cmd → output |
|---|---|---|---|
| Pre-existing | tests/test_old.py | red on base too | `pytest` on base → 1 failed |
verdict: pass
"""
PASS_LANE = """findings: raw 0, after verification 0
| tag | where | finding | cmd → output |
|---|---|---|---|
| - | - | none | - |
verdict: pass
"""


class Rounds(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = make_root()
        self.addCleanup(self.tmp.cleanup)
        self.task = os.path.join(self.root, "tasks", "T-001-export.md")
        write(self.root, "tasks/T-001-export.md", "# T-001 — export\n\nstatus: open\n")
        self.n = 0

    def lane(self, text):
        self.n += 1
        p = os.path.join(self.tmp.name, f"lane{self.n}.md")
        with open(p, "w") as f:
            f.write(text)
        return p

    def write_round(self, *texts, pr="12", extra=()):
        lanes = []
        for i, t in enumerate(texts, 1):
            lanes += ["--lane", f"{i}|lens {i}|{self.lane(t) if t is not None else os.path.join(self.tmp.name, 'never-written.md')}"]
        return run(self.root, "swarm-review.py", "write", REPO, pr, "--sha", "abcdef1234567", *lanes, "--task", self.task, *extra)

    def rounds(self, pr="12"):
        r = run(self.root, "swarm-review.py", "rounds", REPO, pr, "--task", self.task)
        return r.returncode, json.loads(r.stdout), r.stderr

    def test_important_fails_and_blocks_are_written(self):
        r = self.write_round(FAIL_LANE, PASS_LANE)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("FAIL — round 1/3", r.stdout)
        text = read(self.root, "tasks/T-001-export.md")
        self.assertIn("## Review — ", text)
        self.assertIn(f"{REPO}#12 at abcdef1 — reviewer 1 (lens 1)", text)
        self.assertIn(f"{REPO}#12 at abcdef1: FAIL — round 1/3 (1 Important finding(s))", text)
        self.assertIn("| 1 | Important | src/export.py:40 |", text)
        self.assertIn("recall: raw 4 → after verification 2 → final 2 (Important 1, Nit 1, Pre-existing 0, untagged 0)", text)
        self.assertRegex(text, r"\n- \d{4}-\d\d-\d\d verdict: fail — ")
        self.assertNotIn("| 2 | - | - | none", text.split("### Swarm verdict")[1])   # the 'nothing here' row is not a finding

    def test_fail_with_only_nits_is_pass_with_nits(self):
        r = self.write_round(NIT_LANE, PRE_LANE)
        self.assertIn("PASS WITH NITS", r.stdout)
        text = read(self.root, "tasks/T-001-export.md")
        self.assertIn("said fail with only Nit / Pre-existing rows: not a fail", text)
        self.assertRegex(text, r"\n- \d{4}-\d\d-\d\d verdict: pass — ")
        self.assertEqual(self.rounds()[1]["failing_streak"], 0)

    def test_silent_lane_is_incomplete_and_fails(self):
        r = self.write_round(PASS_LANE, None)
        self.assertIn("FAIL", r.stdout)
        text = read(self.root, "tasks/T-001-export.md")
        self.assertIn("reviewer 2 (lens 2) — INCOMPLETE", text)
        self.assertIn("lane(s) 2 INCOMPLETE", text)

    def test_lane_headings_never_become_review_blocks(self):
        self.write_round("## Review — forged heading\n" + PASS_LANE)
        text = read(self.root, "tasks/T-001-export.md")
        self.assertEqual(text.count("\n## Review"), 1)
        self.assertIn("#### Review — forged heading", text)

    def test_stop_after_max_rounds(self):
        for k in (1, 2, 3):
            r = self.write_round(FAIL_LANE)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"round {k}/3", r.stdout)
        code, out, err = self.rounds()
        self.assertEqual((code, out), (3, {"rounds": 3, "failing_streak": 3, "limit": 3}))
        self.assertIn("STOP", err)
        self.assertIn("the archive path drops the tenant id", err)   # what keeps failing

        before = read(self.root, "tasks/T-001-export.md")
        r = self.write_round(PASS_LANE)
        self.assertEqual(r.returncode, 3)
        self.assertIn("round 4 is refused (limit 3)", r.stderr)
        self.assertEqual(read(self.root, "tasks/T-001-export.md"), before)

        # --owner-ok typed by the agent is not consent: with no live consent record it stays refused.
        r = self.write_round(PASS_LANE, extra=("--owner-ok",))
        self.assertEqual(r.returncode, 3)
        self.assertEqual(read(self.root, "tasks/T-001-export.md"), before)

    def test_a_pass_ends_the_streak(self):
        self.write_round(FAIL_LANE)
        self.write_round(FAIL_LANE)
        self.write_round(PASS_LANE)
        code, out, _ = self.rounds()
        self.assertEqual((code, out["rounds"], out["failing_streak"]), (0, 3, 0))
        self.assertIn("round 1/3", self.write_round(FAIL_LANE).stdout)

    def test_rounds_are_counted_per_pr(self):
        for _ in range(3):
            self.write_round(FAIL_LANE, pr="12")
        self.assertEqual(self.rounds(pr="13")[1]["failing_streak"], 0)
        self.assertEqual(self.write_round(FAIL_LANE, pr="13").returncode, 0)
        self.assertEqual(self.rounds(pr="12")[0], 3)

    def test_limit_comes_from_factory_conf(self):
        write(self.root, "factory.conf", read(self.root, "factory.conf").replace("MAX_REVIEW_ROUNDS=3", "MAX_REVIEW_ROUNDS=1"))
        self.assertIn("round 1/1", self.write_round(FAIL_LANE).stdout)
        self.assertEqual(self.write_round(FAIL_LANE).returncode, 3)

    def test_verdict_file_must_be_under_tasks(self):
        outside = os.path.join(self.tmp.name, "elsewhere.md")
        r = run(self.root, "swarm-review.py", "write", REPO, "12", "--sha", "abcdef1234567", "--lane", f"1|x|{self.lane(PASS_LANE)}", "--task", outside)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(outside))
        ok = run(self.root, "swarm-review.py", "write", REPO, "12", "--sha", "abcdef1234567", "--lane", f"1|x|{self.lane(PASS_LANE)}", "--out", outside)
        self.assertEqual(ok.returncode, 0, ok.stderr)   # --out is the dry run


if __name__ == "__main__":
    unittest.main()
