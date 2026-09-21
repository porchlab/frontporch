"""Test real SIP registration and container replacement on an isolated local PBX.

docker build -f asterisk/Dockerfile -t frontporch-asterisk:registration-test .
python deploy/test_asterisk_registration.py

Uses disposable configuration, a unique volume, and an internal Docker network.
Never connects to production or loads real phone credentials.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid


ROOT = Path(__file__).resolve().parent.parent


def docker(*args):
    return subprocess.check_output(
        ["docker", *args], text=True, stderr=subprocess.STDOUT, timeout=90,
    ).strip()


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.prefix = "frontporch-registration-test-" + uuid.uuid4().hex[:10]
        (ROOT / ".local").mkdir(exist_ok=True)
        workspace = tempfile.TemporaryDirectory(prefix=self.prefix, dir=ROOT / ".local")
        self.addCleanup(workspace.cleanup)
        self.workspace = Path(workspace.name)
        # The upstream entrypoint chowns bind-mounted configuration to Asterisk.
        # Restore ownership of this disposable fixture after Compose teardown so
        # a non-root Linux runner can remove its TemporaryDirectory.
        self.addCleanup(
            docker, "run", "--rm", "--network", "none",
            "--volume", f"{self.workspace}:/fixture",
            "--entrypoint", "chown", "python:3.12-slim-bookworm",
            "-Rh", f"{os.getuid()}:{os.getgid()}", "/fixture",
        )
        config = json.loads(docker(
            "compose", "--env-file", str(ROOT / ".env.example"),
            "-f", str(ROOT / "compose.yaml"), "config", "--format", "json",
        ))
        service = config["services"]["asterisk"]
        service.pop("build")
        service["image"] = os.environ.get(
            "FRONTPORCH_ASTERISK_TEST_IMAGE", "frontporch-asterisk:registration-test",
        )
        service.pop("network_mode")
        service["networks"] = ["default"]
        service["restart"] = "no"
        service["environment"] = {"TZ": "UTC"}
        volumes = {}
        for mount in service["volumes"]:
            if mount["type"] == "volume":
                volumes[mount["source"]] = {"name": self.prefix + "-" + mount["source"]}
            else:
                path = self.workspace / mount["target"].lstrip("/")
                path.mkdir(parents=True, exist_ok=True)
                mount["source"] = str(path)
        etc = self.workspace / "etc/asterisk"
        for name in ("asterisk.conf", "pjsip.conf", "modules.conf"):
            shutil.copy(ROOT / "asterisk/etc" / name, etc / name)
        (etc / "extensions.conf").write_text("[default]\nexten => _X!,1,Hangup(21)\n")
        (etc / "conf.d/pjsip_frontporch.conf").write_text("""
[testphone](endpoint-basic)
auth=testphone
aors=testphone
[testphone](auth-userpass)
username=testphone
password=test-only-password
[testphone](aor-single-reg)
""")
        self.compose_file = self.workspace / "compose.json"
        self.compose_file.write_text(json.dumps({
            "services": {
                "asterisk": service,
                "phone": {
                    "image": "python:3.12-slim-bookworm",
                    "command": ["python", "-u", "/test.py", "--client"],
                    "volumes": [f"{Path(__file__).resolve()}:/test.py:ro"],
                    "networks": ["default"],
                },
            },
            "volumes": volumes,
            "networks": {"default": {"internal": True}},
        }))
        self.addCleanup(self.compose, "down", "--volumes", "--remove-orphans")
        self.compose("up", "-d", "--no-deps", "asterisk")
        self.wait_ready()

    def compose(self, *args):
        return docker("compose", "-p", self.prefix, "-f", str(self.compose_file), *args)

    def cli(self, command):
        return self.compose("exec", "-T", "asterisk", "asterisk", "-rx", command)

    def wait_ready(self):
        for _ in range(60):
            try:
                if re.search(r"Aor:\s+testphone\s+1", self.cli("pjsip show aor testphone")):
                    return
            except subprocess.CalledProcessError:
                pass
            time.sleep(0.25)
        self.fail("Test PBX did not start:\n" + self.compose("logs", "asterisk"))

    def wait_for_phone(self, message):
        for _ in range(60):
            if message in self.compose("logs", "phone"):
                return
            time.sleep(0.25)
        self.fail("Test phone failed:\n" + self.compose("logs", "--tail=25", "phone", "asterisk"))

    def test_registration_survives_reload_and_replacement(self):
        self.assertNotRegex(self.cli("pjsip show aor testphone"), r"Contact:\s+testphone/")
        self.compose("up", "-d", "--no-deps", "phone")
        self.wait_for_phone("REGISTERED 300")
        self.assertRegex(self.cli("pjsip show aor testphone"), r"Contact:\s+testphone/")
        saved_contact = self.cli("database show registrar")
        self.assertIn("testphone", saved_contact)

        # The same commands used during an ordinary deployment preserve state.
        container = self.compose("ps", "-q", "asterisk")
        self.compose("up", "-d", "--no-deps", "asterisk")
        self.assertEqual(self.compose("ps", "-q", "asterisk"), container)
        self.cli("module reload res_pjsip.so")
        self.cli("dialplan reload")
        self.assertEqual(self.cli("database show registrar"), saved_contact)

        # Destroy the writable layer, retaining only the production mounts.
        # No further REGISTER is sent: the replacement must recover from AstDB.
        self.compose("up", "-d", "--no-deps", "--force-recreate", "asterisk")
        self.wait_ready()
        self.assertNotEqual(self.compose("ps", "-q", "asterisk"), container)
        self.assertEqual(self.cli("database show registrar"), saved_contact)
        self.assertRegex(self.cli("pjsip show aor testphone"), r"Contact:\s+testphone/")
        self.cli("channel originate PJSIP/testphone application Hangup")
        self.wait_for_phone("INVITE received after registration")

    def test_migrate_existing_database_before_first_replacement(self):
        # Recreate the legacy layout before registering the synthetic phone.
        configuration = json.loads(self.compose_file.read_text())
        self.addCleanup(self.compose_file.write_text, json.dumps(configuration))
        self.compose("down", "--volumes")
        legacy = json.loads(json.dumps(configuration))
        legacy["services"]["asterisk"]["volumes"] = [
            mount for mount in legacy["services"]["asterisk"]["volumes"]
            if mount["target"] != "/var/lib/asterisk"
        ]
        self.compose_file.write_text(json.dumps(legacy))
        self.compose("up", "-d", "--no-deps", "asterisk")
        self.wait_ready()
        self.compose("up", "-d", "--no-deps", "phone")
        self.wait_for_phone("REGISTERED 300")
        saved_contact = self.cli("database show registrar")
        container = self.compose("ps", "-q", "asterisk")

        self.compose("stop", "asterisk")
        backup = self.workspace / "astdb.sqlite3"
        docker("cp", f"{container}:/var/lib/asterisk/astdb.sqlite3", str(backup))
        volume = configuration["volumes"]["asterisk-data"]["name"]
        docker("volume", "create", volume)
        docker(
            "run", "--rm", "--network", "none", "--entrypoint", "sh",
            "-v", f"{volume}:/var/lib/asterisk",
            "-v", f"{backup}:/restore/astdb.sqlite3:ro",
            configuration["services"]["asterisk"]["image"], "-ec",
            "test ! -e /var/lib/asterisk/astdb.sqlite3; "
            "cp /restore/astdb.sqlite3 /var/lib/asterisk/astdb.sqlite3; "
            "chown asterisk:asterisk /var/lib/asterisk/astdb.sqlite3",
        )
        integrity = docker(
            "run", "--rm", "--network", "none",
            "-v", f"{volume}:/data:ro", "python:3.12-slim-bookworm",
            "python", "-c",
            "import sqlite3; "
            "db = sqlite3.connect('file:/data/astdb.sqlite3?mode=ro', uri=True); "
            "print(db.execute('PRAGMA integrity_check').fetchone()[0])",
        )
        self.assertEqual(integrity, "ok")

        self.compose_file.write_text(json.dumps(configuration))
        self.compose("up", "-d", "--no-deps", "asterisk")
        self.wait_ready()
        self.assertNotEqual(self.compose("ps", "-q", "asterisk"), container)
        self.assertEqual(self.cli("database show registrar"), saved_contact)
        self.cli("channel originate PJSIP/testphone application Hangup")
        self.wait_for_phone("INVITE received after registration")


class TestPhone:
    """Synthetic ATA: register once, then receive an INVITE without refreshing."""

    def __init__(self):
        self.destination = ("asterisk", 5060)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        self.sock.settimeout(5)
        self.call_id = uuid.uuid4().hex
        self.sequence = 0

    def register(self, authorization=""):
        self.sequence += 1
        port = self.sock.getsockname()[1]
        lines = [
            "REGISTER sip:pbx.test SIP/2.0",
            f"Via: SIP/2.0/UDP 127.0.0.1:{port};branch=z9hG4bK{uuid.uuid4().hex};rport",
            "From: <sip:testphone@pbx.test>;tag=registration-test",
            "To: <sip:testphone@pbx.test>",
            f"Call-ID: {self.call_id}",
            f"CSeq: {self.sequence} REGISTER",
            f"Contact: <sip:testphone@127.0.0.1:{port}>",
            "Expires: 3600",
            "Max-Forwards: 70",
            "User-Agent: FrontPorch-registration-test",
        ]
        if authorization:
            lines.append("Authorization: " + authorization)
        lines.extend(["Content-Length: 0", "", ""])
        self.sock.sendto("\r\n".join(lines).encode(), self.destination)
        while True:
            response = self.sock.recv(65535).decode()
            if f"CSeq: {self.sequence} REGISTER" in response and not response.startswith("SIP/2.0 100"):
                return response

    def authorization(self, challenge, password):
        fields = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
        realm, nonce = fields["realm"], fields["nonce"]
        def md5(value):
            return hashlib.md5(value.encode()).hexdigest()
        ha1 = md5(f"testphone:{realm}:{password}")
        ha2 = md5("REGISTER:sip:pbx.test")
        cnonce = uuid.uuid4().hex
        digest = md5(f"{ha1}:{nonce}:00000001:{cnonce}:auth:{ha2}")
        header = (
            f'Digest username="testphone", realm="{realm}", nonce="{nonce}", '
            f'uri="sip:pbx.test", response="{digest}", algorithm=MD5, '
            f'qop=auth, nc=00000001, cnonce="{cnonce}"'
        )
        if "opaque" in fields:
            header += f', opaque="{fields["opaque"]}"'
        return header

    def run(self):
        check = unittest.TestCase()
        challenge = self.register()
        check.assertTrue(challenge.startswith("SIP/2.0 401"), challenge)
        rejected = self.register(self.authorization(challenge, "wrong-password"))
        check.assertTrue(rejected.startswith("SIP/2.0 401"), rejected)
        accepted = self.register(self.authorization(rejected, "test-only-password"))
        check.assertTrue(accepted.startswith("SIP/2.0 200"), accepted)
        check.assertIn("\r\nexpires: 300\r\n", accepted.lower())
        # The contact's remaining lifetime may already have rounded down a second.
        remaining = int(re.search(r";expires=(\d+)", accepted.lower()).group(1))
        check.assertGreater(remaining, 0)
        check.assertLessEqual(remaining, 300)
        print("REGISTERED 300", flush=True)
        self.sock.settimeout(60)
        while True:
            data, address = self.sock.recvfrom(65535)
            lines = data.decode().split("\r\n")
            if not lines[0].startswith("INVITE "):
                continue
            headers = [line for line in lines if line.startswith((
                "Via:", "From:", "To:", "Call-ID:", "CSeq:",
            ))]
            reply = "\r\n".join([
                "SIP/2.0 486 Busy Here", *headers, "Content-Length: 0", "", "",
            ])
            self.sock.sendto(reply.encode(), address)
            print("INVITE received after registration", flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--client"]:
        TestPhone().run()
    else:
        unittest.main(verbosity=2)
