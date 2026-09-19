"""Exercise the real nginx ingress with disposable Docker containers.

Run: python deploy/test_public_ingress.py
No NAS access, Cloudflare token, production database or application data is used.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid


ROOT = Path(__file__).resolve().parents[1]


def docker(*arguments, **kwargs):
    return subprocess.check_output(["docker", *arguments], text=True, **kwargs).strip()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class PublicIngressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prefix = "frontporch-ingress-test-" + uuid.uuid4().hex[:10]
        (ROOT / ".local").mkdir(exist_ok=True)
        cls.workspace = tempfile.TemporaryDirectory(prefix=cls.prefix, dir=ROOT / ".local")
        cls.addClassCleanup(cls.workspace.cleanup)
        env = dict(os.environ)
        for line in (ROOT / ".env.example").read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key] = value
        env["ASTERISK_CONF_D_DIR"] = "./asterisk/etc/conf.d"
        cls.config = json.loads(docker(
            "compose", "--env-file", str(ROOT / ".env.example"),
            "-f", str(ROOT / "compose.yaml"), "-f", str(ROOT / "compose.public.yaml"),
            "config", "--format", "json", env=env,
        ))
        docker("network", "create", cls.prefix)
        cls.addClassCleanup(docker, "network", "rm", cls.prefix)
        fixture = Path(cls.workspace.name) / "server.py"
        fixture.write_text('''from http.server import BaseHTTPRequestHandler, HTTPServer
import json
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(dict(self.headers)).encode())
    do_POST = do_GET
    def log_message(self, *args): pass
HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
''')
        cls.backend = cls.prefix + "-backend"
        docker(
            "run", "-d", "--name", cls.backend, "--network", cls.prefix,
            "--network-alias", "portal", "-v", f"{fixture}:/server.py:ro",
            "python:3.12-slim-bookworm", "python", "/server.py",
        )
        cls.addClassCleanup(docker, "rm", "-f", cls.backend)
        cls.ingress = cls.prefix + "-ingress"
        docker(
            "run", "-d", "--name", cls.ingress, "--network", cls.prefix,
            "-p", "127.0.0.1::8080",
            "-e", "FRONTPORCH_PUBLIC_HOST=front.porchlab.app",
            "-e", "NGINX_ENVSUBST_FILTER=^FRONTPORCH_PUBLIC_HOST$",
            "-v", f"{ROOT / 'deploy/public-ingress.conf.template'}:/etc/nginx/templates/default.conf.template:ro",
            cls.config["services"]["public-ingress"]["image"],
        )
        cls.addClassCleanup(docker, "rm", "-f", cls.ingress)
        cls.base_url = "http://" + docker("port", cls.ingress, "8080/tcp")
        cls.opener = build_opener(NoRedirect)
        for attempt in range(50):
            try:
                if cls.request("/welcome/")[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError(
                "The test ingress did not start: "
                + docker("logs", cls.ingress, stderr=subprocess.STDOUT)
                + docker("logs", cls.backend, stderr=subprocess.STDOUT)
            )
        docker("exec", cls.ingress, "nginx", "-t", stderr=subprocess.STDOUT)

    @classmethod
    def request(cls, path, method="GET", **overrides):
        headers = {
            "Host": "front.porchlab.app",
            "X-Forwarded-Proto": "https",
            "CF-Connecting-IP": "192.0.2.10",
            **overrides,
        }
        request = Request(cls.base_url + path, headers=headers, method=method)
        try:
            response = cls.opener.open(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def test_compose_separates_public_and_private_networks(self):
        services = self.config["services"]
        for name in ("portal", "public-ingress", "cloudflared"):
            self.assertFalse(services[name].get("ports"))
        self.assertEqual(set(services["cloudflared"]["networks"]), {"tunnel"})
        self.assertNotIn("default", services["public-ingress"]["networks"])
        self.assertNotIn("tunnel", services["portal"]["networks"])
        self.assertTrue(self.config["networks"]["portal_backend"]["internal"])
        self.assertEqual(services["web"]["ports"][0]["host_ip"], "100.64.0.10")
        self.assertEqual(services["asterisk"]["network_mode"], "host")
        self.assertEqual(services["portal"]["depends_on"]["web"]["condition"], "service_healthy")

    def test_admin_and_encoded_admin_are_blocked(self):
        for path in ("/admin", "/admin/", "/admin/login/", "/a%64min/", "/ADMIN/"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_unknown_hosts_are_rejected(self):
        self.assertEqual(self.request("/", Host="private.example.com")[0], 404)

    def test_http_redirects_to_canonical_https(self):
        status, headers, _ = self.request("/welcome/", **{"X-Forwarded-Proto": "http"})
        self.assertEqual(status, 301)
        self.assertEqual(headers["Location"], "https://front.porchlab.app/welcome/")

    def test_proxy_overwrites_untrusted_forwarding_headers(self):
        status, _, body = self.request("/", **{
            "X-Forwarded-For": "198.51.100.20",
            "X-Forwarded-Host": "evil.example.com",
            "Forwarded": "host=evil.example.com;proto=http",
        })
        self.assertEqual(status, 200)
        headers = {key.lower(): value for key, value in json.loads(body).items()}
        self.assertEqual(headers["host"], "front.porchlab.app")
        self.assertEqual(headers["x-forwarded-proto"], "https")
        self.assertEqual(headers["x-forwarded-for"], "192.0.2.10")
        self.assertNotIn("x-forwarded-host", headers)
        self.assertNotIn("forwarded", headers)

    def test_login_rate_limit_is_per_client_and_covers_encoded_paths(self):
        codes = [self.request("/accounts/login/", "POST")[0] for _ in range(10)]
        self.assertEqual(codes[0], 200)
        self.assertIn(429, codes)
        self.assertEqual(self.request("/accounts/%6cogin/", "POST")[0], 429)
        self.assertEqual(self.request("/accounts/login/")[0], 200)
        self.assertEqual(self.request("/accounts/login/", "POST", **{
            "CF-Connecting-IP": "192.0.2.11"
        })[0], 200)

    def test_invitation_tokens_are_not_in_access_logs(self):
        token = "test-private-invitation-token"
        self.assertEqual(self.request(f"/guardians/join/{token}/")[0], 200)
        logs = docker("logs", self.ingress, stderr=subprocess.STDOUT)
        self.assertNotIn(token, logs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
