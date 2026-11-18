"""A throwaway factory root for the tests: factory.conf, empty ledgers, an empty mistake store. No network."""
import os
import subprocess
import sys
import tempfile

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = '''CLIENT_NAME="Example Co"
CLIENT_SLUG=example
OWNER_NAME="Owner"
CLIENT_REPOS="../example-app"
CLIENT_CONTACT_EMAILS="pat@client.example @partner.example"
MAIL_CLI="{mail_cli}"
MAX_REVIEW_ROUNDS=3
'''
HEADERS = {
    "ledger/mail.tsv": "date_utc\tmsgid\tthread\tdir\tfrom\tto\tsubject\tattachments\ttask\tasks\tnote",
    "ledger/asks.tsv": "ask_id\ttask\tthread\tfirst_msgid\tdate_utc\tto\twording\tstatus\tanswered_by\tchase_after\tnote",
    "ledger/promises.tsv": "promise_id\ttask\tmsgid\tdate_utc\tto\twording\tdue\tstatus\tevidence",
    "ledger/claims.tsv": "claim_id\ttold_in_msgid\tdate_utc\tclaim_to_client\tverify_cmd\tlast_verified\tstill_true",
    "learning/mistakes.tsv": "id\tline\tdate\tprimary\tinvolved\tcaught_by\treached\tactor\ttrigger\trule\tmechanism\tproposed\tsummary\tinferred",
}
RULES = """# RULES

<!-- counts:begin -->
| # | Shape | The rule | Mechanism | primary / involved |
|---|---|---|---|---|
| P1 | Claim without the falsifying command | rule text | a gate | 0 / 0 |
| P5 | The check could only confirm what was expected | rule text | a reviewer | 0 / 0 |
<!-- counts:end -->

Text after the block stays.
"""


def make_root(mail_cli="no-such-mail-cli"):
    """(TemporaryDirectory, root path). The root sits one level down so '../example-app' stays inside the temp dir."""
    tmp = tempfile.TemporaryDirectory()
    root = os.path.join(tmp.name, "ops")
    for d in ("ledger", "learning", "tasks", "state"):
        os.makedirs(os.path.join(root, d))
    write(root, "factory.conf", CONF.format(mail_cli=mail_cli))
    for rel, head in HEADERS.items():
        write(root, rel, head + "\n")
    write(root, "learning/MISTAKE.md", "# MISTAKE\n")
    write(root, "RULES.md", RULES)
    write(root, "STATE.md", "# STATE\n")
    return tmp, root


def write(root, rel, text):
    with open(os.path.join(root, rel), "w") as f:
        f.write(text)


def read(root, rel):
    with open(os.path.join(root, rel)) as f:
        return f.read()


def run(root, script, *args):
    env = dict(os.environ, FACTORY_ROOT=root, FACTORY_STATE_DIR=os.path.join(root, "state"))
    cmd = ["bash" if script.endswith(".sh") else sys.executable, os.path.join(SCRIPTS, script), *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=root)
