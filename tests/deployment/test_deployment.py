import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"deploy/automation/{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


gate = module("verify_revision")
policy = module("check_workflows")
http = module("verify_http")
SHA = "a" * 40


class RevisionTests(unittest.TestCase):
    def fixture(self, *, conclusion="success", event="push", workflow_path=None, head=SHA):
        def get(path):
            if path.endswith("/git/ref/heads/main"):
                return {"object": {"sha": head}}
            if "/workflows/" in path:
                file = path.split("/workflows/")[1].split("/")[0]
                return {"workflow_runs": [{"id": 1 if file == "tests.yml" else 2,
                    "head_sha": SHA, "event": event, "head_branch": "main",
                    "path": workflow_path or f".github/workflows/{file}",
                    "repository": {"full_name": "porchlab/frontporch"},
                    "head_repository": {"full_name": "porchlab/frontporch"}}]}
            names = ("tests", "deployment-policy") if "/runs/1/" in path else ("parity",)
            return {"jobs": [{"name": name, "status": "completed", "conclusion": conclusion} for name in names]}
        return get

    def test_only_successful_main_workflow_jobs_authorize(self):
        self.assertTrue(gate.authorized("porchlab/frontporch", SHA, self.fixture()))

    def test_rejects_superseded_revision(self):
        with self.assertRaises(ValueError):
            gate.authorized("porchlab/frontporch", SHA, self.fixture(head="b" * 40))

    def test_failed_or_skipped_jobs_do_not_authorize(self):
        for conclusion in ("failure", "skipped", "cancelled", "neutral"):
            with self.subTest(conclusion=conclusion), self.assertRaises(ValueError):
                gate.authorized("porchlab/frontporch", SHA, self.fixture(conclusion=conclusion))

    def test_pr_and_wrong_workflow_cannot_spoof_checks(self):
        for options in ({"event": "pull_request"}, {"workflow_path": ".github/workflows/forged.yml"}):
            self.assertFalse(gate.authorized("porchlab/frontporch", SHA, self.fixture(**options)))

    def test_malformed_revision_is_rejected_before_network(self):
        with self.assertRaises(ValueError):
            gate.authorized("porchlab/frontporch", "main; touch /tmp/no", lambda _: self.fail("network called"))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / ".github", self.root / ".github")
        shutil.copytree(ROOT / "deploy/automation", self.root / "deploy/automation")
        self.addCleanup(self.temp.cleanup)

    def test_current_workflows(self):
        policy.check(self.root)

    def test_rejects_sensitive_workflow_mutations(self):
        file = self.root / ".github/workflows/tests.yml"
        original = file.read_text()
        for before, after in (
            ("pull_request:", "pull_request_target:"),
            ("id-token: write", "id-token: read"),
            ("environment: production", "environment: staging"),
            ("--accept-routes=false", "--accept-routes=true"),
            ("StrictHostKeyChecking=yes", "StrictHostKeyChecking=no"),
            ("needs: [tests, deployment-policy]", "needs: []"),
            ("cancel-in-progress: false", "cancel-in-progress: true"),
        ):
            with self.subTest(after=after):
                file.write_text(original.replace(before, after))
                with self.assertRaises(AssertionError):
                    policy.check(self.root)
        file.write_text(original)

    def test_rejects_new_credential_job(self):
        file = self.root / ".github/workflows/other.yml"
        file.write_text('on: {pull_request: null}\npermissions: {contents: read}\njobs:\n  bad:\n    runs-on: ubuntu-latest\n    environment: production\n')
        with self.assertRaises(AssertionError):
            policy.check(self.root)

    def test_duplicate_yaml_keys_fail_closed(self):
        file = self.root / ".github/workflows/tests.yml"
        file.write_text(file.read_text() + "\npermissions: write-all\n")
        with self.assertRaises(ValueError):
                policy.check(self.root)


class HttpTests(unittest.TestCase):
    def test_redirects_never_reach_an_alternate_origin_route(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from threading import Thread

        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if self.path == "/alternate-route":
                    self.send_response(200)
                else:
                    self.send_response(int(self.path.lstrip("/")))
                    self.send_header("Location", "/alternate-route")
                self.send_header("Cache-Control", "private, no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_):
                pass

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            worker = Thread(target=lambda: server.serve_forever(poll_interval=0.01))
            worker.start()
            try:
                for code in (301, 302, 303, 307, 308):
                    with self.subTest(code=code):
                        observed, _ = http.status(f"http://127.0.0.1:{server.server_port}/{code}")
                        self.assertEqual(observed, code)
                self.assertNotIn("/alternate-route", requests)
            finally:
                server.shutdown()
                worker.join(timeout=5)

    def test_public_routes_and_headers(self):
        from unittest.mock import patch
        calls = []

        def response(url, headers):
            calls.append((url, headers))
            return (404 if "/admin" in url else 200), {"Cache-Control": "private, no-store"}

        with patch.object(http, "status", response):
            http.verify("parents.example.com")
        self.assertEqual(len(calls), 5)
        self.assertTrue(all(url.startswith("http://public-ingress:8080/") for url, _ in calls))
        self.assertTrue(all(headers == {"Host": "parents.example.com", "X-Forwarded-Proto": "https"} for _, headers in calls))

    def test_public_admin_exposure_and_html_caching_fail(self):
        from unittest.mock import patch
        for headers in ({"Cache-Control": "private, no-store"}, {"Cache-Control": "public"}):
            with patch.object(http, "status", return_value=(200, headers)):
                with self.assertRaises(RuntimeError):
                    http.verify("parents.example.com")


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        (self.root / "backup").mkdir()
        shutil.copy(ROOT / "deploy/automation/receive.sh", self.root / "receive.sh")
        self.calls = self.root / "calls"
        docker = self.root / "docker"
        # Fake only external tools, exercising the actual host shell control flow.
        docker.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$(dirname "$0")/calls"
if [ -f "$(dirname "$0")/fail" ]; then
  pattern=$(cat "$(dirname "$0")/fail")
  case "$*" in *"$pattern"*) exit 1;; esac
fi
case "$*" in
  *'remote get-url origin'*) echo git@github.com:porchlab/frontporch.git;;
  *'branch --show-current'*) echo main;;
  *'status --porcelain'*) test ! -f "$(dirname "$0")/dirty" || echo ' M compose.yaml';;
  *'rev-parse FETCH_HEAD'*) echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;;
  *'rev-parse HEAD'*) echo bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb;;
  *'pg_dump'*) echo archive;;
  *'ps --all -q'*|*'ps -q db'*) echo container;;
  *'.State.Status'*) echo running;;
  *'.State.Health.Status'*)
    if [ -f "$(dirname "$0")/fail-completion" ]; then
      rm "$(dirname "$0")/state/stage"
      mkdir "$(dirname "$0")/state/stage"
    fi
    echo healthy;;
esac
exit 0
''')
        docker.chmod(0o700)
        values = {"DOCKER": docker, "CHECKOUT": self.root, "STATE_DIR": self.state,
                  "BACKUP_DIR": self.root / "backup", "SSH_DIR": self.root,
                  "ORIGIN": "git@github.com:porchlab/frontporch.git", "PROJECT": "frontporch",
                  "REPOSITORY": "porchlab/frontporch", "PYTHON_IMAGE": "python-pinned", "GIT_IMAGE": "git-pinned"}
        import shlex
        (self.root / "config.sh").write_text("\n".join(f"{key}={shlex.quote(str(value))}" for key, value in values.items()))
        (self.state / "enabled").touch()

    def run_receiver(self, command=SHA):
        return subprocess.run(["sh", str(self.root / "receive.sh"), command], capture_output=True, text=True, timeout=10)

    def test_arbitrary_commands_and_short_sha_never_reach_docker(self):
        for command in ("", "main", "a" * 39, "a" * 41, SHA + "; id", SHA + "\nwhoami", "-h"):
            self.assertNotEqual(self.run_receiver(command).returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_lock_and_disabled_state_block_execution(self):
        (self.state / "lock").mkdir()
        self.assertNotEqual(self.run_receiver().returncode, 0)
        (self.state / "lock").rmdir()
        (self.state / "enabled").unlink()
        self.assertNotEqual(self.run_receiver().returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_dirty_checkout_is_preserved(self):
        (self.root / "dirty").touch()
        self.assertNotEqual(self.run_receiver().returncode, 0)
        self.assertNotIn("merge --ff-only", self.calls.read_text())
        self.assertFalse((self.state / "failed").exists())

    def test_failure_stops_later_stages_and_requires_recovery(self):
        for failure, forbidden in (("build web", "pg_dump"), ("pg_dump", "--force-recreate"),
                                   ("--wait-timeout", "render_asterisk_config"),
                                   ("render_asterisk_config", "verify_http.py")):
            with self.subTest(failure=failure):
                (self.root / "fail").write_text(failure)
                self.calls.unlink(missing_ok=True)
                (self.state / "failed").unlink(missing_ok=True)
                self.assertNotEqual(self.run_receiver().returncode, 0)
                calls = self.calls.read_text()
                self.assertNotIn(forbidden, calls)
                self.assertTrue((self.state / "failed").exists())
                self.assertFalse((self.state / "lock").exists())
                self.assertNotEqual(self.run_receiver().returncode, 0)
                self.assertEqual(self.calls.read_text(), calls)

    def test_success_order_and_no_database_restart(self):
        result = self.run_receiver()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls.read_text()
        stages = ["verify_revision.py", "merge --ff-only", "build web", "pg_dump", "--wait-timeout", "--force-recreate portal", "render_asterisk_config", "verify_http.py"]
        self.assertEqual(sorted(calls.index(stage) for stage in stages), [calls.index(stage) for stage in stages])
        self.assertNotIn("up -d db", calls)
        self.assertNotIn("--force-recreate asterisk", calls)
        self.assertEqual((self.state / "deployed-revision").read_text().strip(), SHA)
        self.assertFalse((self.state / "failed").exists())
        self.assertFalse((self.state / "lock").exists())

    def test_failed_completion_write_preserves_recovery_latch(self):
        (self.root / "fail-completion").touch()
        result = self.run_receiver()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.state / "failed").read_text().strip(), SHA)
        self.assertFalse((self.state / "lock").exists())
        calls = self.calls.read_text()
        self.assertNotEqual(self.run_receiver().returncode, 0)
        self.assertEqual(self.calls.read_text(), calls)
