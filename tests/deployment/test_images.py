import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required")
class ComposeTests(unittest.TestCase):
    def config(self, registry=False, environment=None, vpn=False):
        arguments = ["docker", "compose", "--env-file", str(ROOT / ".env.example"),
                     "-f", str(ROOT / "compose.yaml"), "-f", str(ROOT / "compose.public.yaml")]
        if vpn:
            arguments += ["-f", str(ROOT / "compose.wireguard.yaml")]
        if registry:
            arguments += ["-f", str(ROOT / "compose.registry.yaml")]
            if vpn:
                arguments += ["-f", str(ROOT / "compose.wireguard.registry.yaml")]
        if vpn:
            arguments += ["--profile", "wp816"]
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

    def test_vpn_opt_in_limits_privileges_and_separates_secrets_and_status_mounts(self):
        environment = {**os.environ,
                       "FRONTPORCH_WEB_IMAGE": "ghcr.io/porchlab/frontporch@sha256:" + "c" * 64,
                       "FRONTPORCH_ASTERISK_IMAGE": "ghcr.io/porchlab/frontporch-asterisk@sha256:" + "d" * 64,
                       "FRONTPORCH_VPN_DIR": "/operator/private-vpn", "FRONTPORCH_VPN_BIND_IP": "192.0.2.10",
                       "WIREGUARD_SERVER_ADDRESS": "10.77.0.1/24", "WIREGUARD_SERVER_PUBLIC_KEY": "fixture-key",
                       "WIREGUARD_ENCRYPTION_KEY": "fixture-cipher", "WIREGUARD_ENDPOINT": "vpn.example.com:51820"}
        result = self.config(registry=True, vpn=True, environment=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        for name in ("wireguard", "vpn-reconciler"):
            service = services[name]
            self.assertEqual(service["image"], environment["FRONTPORCH_WEB_IMAGE"])
            self.assertNotIn("build", service)
            self.assertTrue(service["read_only"])
            self.assertEqual(service["cap_drop"], ["ALL"])
            self.assertNotIn("network_mode", service)
            self.assertFalse(service.get("privileged", False))
            self.assertTrue(all(mount["source"].startswith("/operator/private-vpn/") for mount in service["volumes"]))
        server, worker = services["wireguard"], services["vpn-reconciler"]
        self.assertEqual(set(server["cap_add"]), {"NET_ADMIN", "NET_RAW"})
        self.assertFalse(worker.get("cap_add"))
        self.assertNotIn("DATABASE_URL", server["environment"])
        self.assertNotIn("WIREGUARD_ENCRYPTION_KEY", server["environment"])
        self.assertEqual(services["portal"]["environment"]["WIREGUARD_ENCRYPTION_KEY"], "")
        server_mounts = {mount["source"].rsplit("/", 1)[-1]: mount for mount in server["volumes"]}
        worker_mounts = {mount["source"].rsplit("/", 1)[-1]: mount for mount in worker["volumes"]}
        self.assertTrue(server_mounts["desired"]["read_only"])
        self.assertFalse(server_mounts["observed"].get("read_only", False))
        self.assertFalse(worker_mounts["desired"].get("read_only", False))
        self.assertTrue(worker_mounts["observed"]["read_only"])
        self.assertTrue(worker_mounts["network.json"]["read_only"])
        self.assertNotIn("config", worker_mounts)
        self.assertEqual(server["ports"][0]["host_ip"], "192.0.2.10")
        self.assertEqual(server["ports"][0]["protocol"], "udp")
