"""check-conf.py reads the fork's own factory.conf: placeholders and empty guard keys fail, real values pass."""
import unittest

import _fixture as fx

GOOD = '''CLIENT_NAME="Northwind"
CLIENT_SLUG=northwind
OWNER_NAME="Robin"
CLIENT_REPOS="../northwind-app"
CLIENT_CONTACT_EMAILS="pat@northwind.test"
MAIL_CLI="env X=1 no-such-mail-cli"
PROD_MARKERS="northwind-prod 222222222222"
DEV_MARKERS="northwind-dev 333333333333"
'''


class CheckConf(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = fx.make_root()
        self.addCleanup(self.tmp.cleanup)

    def run_with(self, conf):
        fx.write(self.root, "factory.conf", conf)
        return fx.run(self.root, "check-conf.py")

    def test_real_values_pass(self):
        r = self.run_with(GOOD)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 fail", r.stdout)

    def test_empty_markers_fail(self):
        r = self.run_with(GOOD.replace('PROD_MARKERS="northwind-prod 222222222222"', 'PROD_MARKERS=""'))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("PROD_MARKERS is empty", r.stdout)

    def test_template_placeholders_fail(self):
        r = self.run_with(GOOD.replace("northwind", "acme"))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("template placeholder", r.stdout)

    def test_short_marker_warns_and_bare_env_assignment_fails(self):
        r = self.run_with(GOOD.replace("northwind-prod 222222222222", "main 222222222222")
                              .replace('"env X=1 no-such-mail-cli"', '"X=1 no-such-mail-cli"'))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("marker 'main'", r.stdout)
        self.assertIn("env VAR=value", r.stdout)


if __name__ == "__main__":
    unittest.main()
