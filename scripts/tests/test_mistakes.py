import unittest

from _fixture import make_root, read, run, write

NEW = ("new", "--caught-by", "self-later", "--actor", "main")


class Mistakes(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = make_root()
        self.addCleanup(self.tmp.cleanup)

    def m(self, *args):
        return run(self.root, "mistakes.py", *args)

    def test_empty_store_is_consistent(self):
        self.assertEqual(self.m("next").stdout.strip(), "1")
        r = self.m("check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_new_needs_a_mechanism_or_prose_only(self):
        r = self.m(*NEW, "--shape", "P5", "--reached", "nobody", "--summary", "x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--prose-only", r.stderr)
        self.assertEqual(read(self.root, "learning/MISTAKE.md"), "# MISTAKE\n")

    def test_reached_values(self):
        for ok in ("nobody", "file", "owner", "client-draft", "client-sent", "prod", "public", "unknown"):
            r = self.m(*NEW, "--shape", "P1", "--reached", ok, "--summary", f"reached {ok}", "--prose-only")
            self.assertEqual(r.returncode, 0, r.stderr)
        r = self.m(*NEW, "--shape", "P1", "--reached", "everyone", "--summary", "x", "--prose-only")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--reached must be one of", r.stderr)

    def test_new_counts_write_check_show(self):
        r = self.m(*NEW, "--shape", "P5", "--involved", "P1", "--reached", "file", "--summary", "row count taken as proof",
                   "--mechanism", "reviewer agent")
        self.assertEqual(r.stdout.strip(), "1", r.stderr)
        r = self.m(*NEW, "--shape", "P1", "--reached", "client-draft", "--summary", "blocked claimed without a command",
                   "--trigger", r"\bblocked\b")
        self.assertEqual(r.stdout.strip(), "2", r.stderr)
        self.assertEqual(self.m("next").stdout.strip(), "3")
        self.assertEqual(self.m("counts").stdout.split("\n")[:2], ["P1\t1\t2", "P5\t1\t1"])

        stale = self.m("check")   # RULES.md still says 0 / 0
        self.assertEqual(stale.returncode, 2)
        self.assertIn("RULES.md says P1 0 / 0; the table says 1 / 2", stale.stdout)

        self.assertEqual(self.m("counts", "--write").returncode, 0)
        rules = read(self.root, "RULES.md")
        self.assertIn("| P1 | Claim without the falsifying command | rule text | a gate | 1 / 2 |", rules)
        self.assertIn("| P5 | The check could only confirm what was expected | rule text | a reviewer | 1 / 1 |", rules)
        self.assertTrue(rules.endswith("Text after the block stays.\n"))
        ok = self.m("check")
        self.assertEqual(ok.returncode, 0, ok.stdout)
        self.assertIn("2 entries, table and RULES.md agree", ok.stdout)

        shown = self.m("show", "2").stdout
        self.assertIn("## 2 — blocked claimed without a command", shown)
        self.assertNotIn("row count taken as proof", shown)

    def test_number_is_top_heading_plus_one_not_count(self):
        write(self.root, "learning/MISTAKE.md", "# MISTAKE\n\n## 7 — an old entry (2020-01-01)\n")
        self.assertEqual(self.m("next").stdout.strip(), "8")

    def test_shape_missing_from_card_gets_a_row(self):
        self.m(*NEW, "--shape", "P9", "--reached", "nobody", "--summary", "logs in tmp", "--prose-only")
        self.m("counts", "--write")
        self.assertIn("| P9 | 1 / 1 |", read(self.root, "RULES.md"))
        self.assertEqual(self.m("check").returncode, 0)

    def test_owed_after_two_prose_only(self):
        for s in ("one", "two"):
            self.m(*NEW, "--shape", "P5", "--reached", "nobody", "--summary", s, "--prose-only")
        self.m("counts", "--write")
        self.assertIn("OWED", self.m("check").stdout)

    def test_edit_above_an_entry_is_caught_then_relinked(self):
        self.m(*NEW, "--shape", "P5", "--reached", "nobody", "--summary", "one", "--mechanism", "hook")
        self.m("counts", "--write")
        write(self.root, "learning/MISTAKE.md", "# MISTAKE\n\nA new intro line.\n" + read(self.root, "learning/MISTAKE.md")[len("# MISTAKE\n"):])
        self.assertEqual(self.m("check").returncode, 2)
        self.assertEqual(self.m("relink").returncode, 0)
        self.assertEqual(self.m("check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
