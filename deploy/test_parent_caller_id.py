"""Check caller ID in real SIP INVITEs from the generated ring-both route.

docker build -f asterisk/Dockerfile -t frontporch-asterisk:registration-test .
uv run python -m deploy.test_parent_caller_id

Uses a disposable PBX with no network access and fictional loopback destinations.
No database, production configuration, or real phone credentials are loaded.
"""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest
import uuid

from directory.asterisk.domain import (
    AsteriskConfiguration,
    DialplanRule,
    ParentPhoneEndpoint,
    SipEndpoint,
)
from directory.asterisk.renderer import AsteriskConfigRenderer


def docker(*args):
    return subprocess.check_output(
        ["docker", *args], text=True, stderr=subprocess.STDOUT, timeout=30
    ).strip()


class ParentCallerIdTests(unittest.TestCase):
    def test_ring_both_sends_child_identity_internally_and_provider_identity_to_trunk(
        self,
    ):
        child = SipEndpoint(
            1,
            "child",
            1,
            "Fictional child",
            1,
            "5301",
            "fictional-child",
            "fixture-secret",
            child_id=1,
        )
        parent = SipEndpoint(
            2,
            "parent",
            2,
            "Fictional parent",
            1,
            "5300",
            "fictional-parent",
            "fixture-secret",
        )
        mobile = ParentPhoneEndpoint(
            2, 2, "Fictional parent", 1, "5300", "+12025550188"
        )
        configuration = AsteriskConfiguration(
            endpoints=(child, parent),
            dialplan_rules=(DialplanRule(child, parent), DialplanRule(child, mobile)),
            outbound_caller_id="2025550199",
        )
        dialplan = AsteriskConfigRenderer().render_extensions(configuration)
        dialplan += (
            "\n[caller-id-test]\n"
            "exten => s,1,Set(CALLERID(num)=5301)\n"
            " same => n,Goto(frontporch-fictional-child,5300,1)\n"
        )
        pjsip = (
            "[transport-loopback]\ntype=transport\nprotocol=udp\n"
            "bind=127.0.0.1:5060\n\n"
        )
        for name, port in (("fictional-parent", 5098), ("voipms-endpoint", 5099)):
            pjsip += (
                f"[{name}]\ntype=endpoint\ntransport=transport-loopback\n"
                f"context=deny\ndisallow=all\nallow=ulaw\naors={name}\n\n"
                f"[{name}]\ntype=aor\ncontact=sip:fictional@127.0.0.1:{port}\n\n"
            )

        workspace = tempfile.TemporaryDirectory(prefix="frontporch-caller-id-")
        self.addCleanup(workspace.cleanup)
        container = "frontporch-caller-id-" + uuid.uuid4().hex[:10]
        image = os.environ.get(
            "FRONTPORCH_ASTERISK_TEST_IMAGE", "frontporch-asterisk:registration-test"
        )
        docker(
            "create",
            "--name",
            container,
            "--network",
            "none",
            "--entrypoint",
            "/usr/sbin/asterisk",
            image,
            "-f",
            "-vvv",
            "-g",
        )
        self.addCleanup(docker, "rm", "--force", container)
        for name, content in (
            ("extensions.conf", dialplan),
            ("pjsip.conf", pjsip),
            ("modules.conf", "[modules]\nautoload=yes\n"),
        ):
            path = Path(workspace.name) / name
            path.write_text(content)
            docker("cp", str(path), f"{container}:/etc/asterisk/{name}")
        docker("start", container)

        def cli(command):
            return docker("exec", container, "asterisk", "-rx", command)

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if "voipms-endpoint" in cli("pjsip show endpoints"):
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(0.1)
        else:
            self.fail("Test PBX did not start:\n" + docker("logs", container))

        cli("core waitfullybooted")
        cli("pjsip set logger on")
        cli("channel originate Local/s@caller-id-test application Wait 1")
        deadline = time.monotonic() + 15
        identities = {}
        while time.monotonic() < deadline:
            logs = docker("logs", container)
            for port, headers in re.findall(
                r"INVITE sip:[^\n]+:(5098|5099) SIP/2\.0\n(.*?)\n\n",
                logs,
                re.DOTALL,
            ):
                identity = re.search(r"^From:.*<sip:([^@>]+)@", headers, re.MULTILINE)
                self.assertIsNotNone(identity, headers)
                identities[port] = identity.group(1)
            if len(identities) == 2:
                break
            time.sleep(0.1)
        # Inspect actual INVITEs: callee CALLERID() values do not establish what
        # PJSIP sent. Its outbound identity comes from CONNECTEDLINE instead.
        self.assertEqual(identities, {"5098": "5301", "5099": "2025550199"}, logs)


if __name__ == "__main__":
    unittest.main()
