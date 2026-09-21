import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required")
class ComposeTests(unittest.TestCase):
    def config(self, registry=False, environment=None):
        arguments = ["docker", "compose", "--env-file", str(ROOT / ".env.example"),
                     "-f", str(ROOT / "compose.yaml"), "-f", str(ROOT / "compose.public.yaml")]
        if registry:
            arguments += ["-f", str(ROOT / "compose.registry.yaml")]
        return subprocess.run([*arguments, "config", "--format", "json"], env=environment,
                              text=True, capture_output=True)

    def test_registry_overlay_shares_django_image_and_preserves_networks_and_volumes(self):
        environment = {**os.environ,
                       "FRONTPORCH_WEB_IMAGE": "ghcr.io/porchlab/frontporch@sha256:" + "c" * 64,
                       "FRONTPORCH_ASTERISK_IMAGE": "ghcr.io/porchlab/frontporch-asterisk@sha256:" + "d" * 64}
        local = self.config(environment=environment)
        production = self.config(registry=True, environment=environment)
        self.assertEqual(production.returncode, 0, production.stderr)
        self.assertEqual(local.returncode, 0, local.stderr)
        before, after = json.loads(local.stdout), json.loads(production.stdout)
        for name in ("web", "portal", "asterisk"):
            self.assertNotIn("build", after["services"][name])
            self.assertEqual(after["services"][name]["image"], environment[
                "FRONTPORCH_ASTERISK_IMAGE" if name == "asterisk" else "FRONTPORCH_WEB_IMAGE"])
            for service in (before["services"][name], after["services"][name]):
                service.pop("build", None)
                service.pop("image", None)
        self.assertEqual(before, after)
        pbx_mounts = after["services"]["asterisk"]["volumes"]
        self.assertTrue(any(mount["source"] == "asterisk-data" and mount["target"] == "/var/lib/asterisk"
                            for mount in pbx_mounts))

    def test_registry_overlay_has_no_default_image_or_build_fallback(self):
        environment = {name: value for name, value in os.environ.items()
                       if name not in ("FRONTPORCH_WEB_IMAGE", "FRONTPORCH_ASTERISK_IMAGE")}
        result = self.config(registry=True, environment=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("set the release image digest", result.stderr)
