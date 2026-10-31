import base64
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from frontporch.vpn_config import (
    ServerConfig, VPNConfigurationError, firewall_config, parse_snapshot, wireguard_config,
)
from frontporch.vpn_runtime import VPNRuntimeError, atomic_private_file, command, read_json, verify_namespace


SERVER_KEY = base64.b64encode(b"s" * 32).decode()
PEER_KEY = base64.b64encode(b"p" * 32).decode()
PSK = base64.b64encode(b"k" * 32).decode()
SERVER = {
    "address": "10.77.0.1/24", "egress_address": "10.77.1.2", "pbx_address": "10.77.1.1",
    "private_key": SERVER_KEY, "listen_port": 51821, "sip_port": 5060,
    "rtp_start": 10000, "rtp_end": 20000, "mtu": 1380,
}
PEER = {"id": "00000000-0000-4000-8000-000000000001", "address": "10.77.0.2",
        "public_key": PEER_KEY, "preshared_key": PSK, "persistent_keepalive": 25}


def snapshot(**overrides):
    return {"schema": 1, "revision": "00000000-0000-4000-8000-000000000002",
            "generated_at": 1000, "expires_at": 1300, "peers": [dict(PEER)], **overrides}


class WireGuardConfigurationTests(SimpleTestCase):
    def setUp(self):
        self.server = ServerConfig.parse(SERVER)

    def test_complete_snapshot_uses_only_host_routes_and_omission_revokes(self):
        peers = parse_snapshot(snapshot(), self.server, 1001).peers
        text = wireguard_config(self.server, peers)
        self.assertIn("AllowedIPs = 10.77.0.2/32", text)
        self.assertIn(f"PresharedKey = {PSK}", text)
        empty = parse_snapshot(snapshot(peers=[]), self.server, 1001)
        self.assertNotIn("[Peer]", wireguard_config(self.server, empty.peers))
        self.assertNotIn(SERVER_KEY, repr(self.server))
        self.assertNotIn(PSK, repr(peers))

    def test_expired_future_unbounded_and_nonfinite_leases_fail_closed(self):
        for values in ({"expires_at": 1001}, {"generated_at": 1032}, {"expires_at": 4601},
                       {"generated_at": float("nan")}, {"expires_at": float("inf")},
                       {"generated_at": True}, {"schema": True}):
            with self.subTest(values=values), self.assertRaises(VPNConfigurationError):
                parse_snapshot(snapshot(**values), self.server, 1001)

    def test_spoofed_peer_networks_server_and_non_hosts_rejected(self):
        for address in ("0.0.0.0/0", "10.77.0.0", "10.77.0.255", "10.77.0.1",
                        "10.77.1.1", "192.168.1.1", "8.8.8.8", "::1", "10.77.0.2\nPostUp=bad"):
            with self.subTest(address=address), self.assertRaises(VPNConfigurationError):
                parse_snapshot(snapshot(peers=[{**PEER, "address": address}]), self.server, 1001)

    def test_duplicate_peer_identity_key_and_address_are_rejected(self):
        other = {**PEER, "id": "00000000-0000-4000-8000-000000000003", "address": "10.77.0.3",
                 "public_key": base64.b64encode(b"q" * 32).decode()}
        for field in ("id", "address", "public_key"):
            with self.subTest(field=field), self.assertRaises(VPNConfigurationError):
                parse_snapshot(snapshot(peers=[PEER, {**other, field: PEER[field]}]), self.server, 1001)

    def test_malformed_or_additional_config_cannot_inject_commands(self):
        for values in ({"private_key": SERVER_KEY + "\nPostUp=bad"}, {"private_key": []},
                       {"listen_port": True}, {"mtu": 9000}, {"address": "0.0.0.0/0"},
                       {"pbx_address": "8.8.8.8"}, {"pbx_address": "10.77.0.3"},
                       {"rtp_start": 22000}, {"command": "bad"}):
            with self.subTest(values=list(values)), self.assertRaises(VPNConfigurationError) as ctx:
                ServerConfig.parse({**SERVER, **values})
            self.assertNotIn(SERVER_KEY, str(ctx.exception))
        with self.assertRaises(VPNConfigurationError):
            parse_snapshot(snapshot(peers=[{**PEER, "PostUp": "bad"}]), self.server, 1001)

    def test_firewall_is_default_deny_and_only_forwards_to_pbx_calling_ports(self):
        text = firewall_config(self.server)
        self.assertIn(":INPUT DROP", text)
        self.assertIn(":FORWARD DROP", text)
        rules = [line for line in text.splitlines() if line.startswith("-A FORWARD")]
        self.assertEqual(len(rules), 2)
        self.assertIn("-i wg0 -o eth0 -d 10.77.1.1/32 -p udp", rules[0])
        self.assertIn("--dports 5060,10000:20000", rules[0])
        self.assertIn("-i eth0 -o wg0 -s 10.77.1.1/32", rules[1])
        self.assertIn("--ctstate ESTABLISHED,RELATED", rules[1])

    def test_reconciler_metadata_needs_no_server_secret_and_cannot_render_server_keys(self):
        network = {name: value for name, value in SERVER.items() if name != "private_key"}
        server = ServerConfig.parse(network, require_private_key=False)
        self.assertEqual(parse_snapshot(snapshot(), server, 1001).peers[0].public_key, PEER_KEY)
        with self.assertRaises(VPNConfigurationError):
            wireguard_config(server, ())
        with self.assertRaises(VPNConfigurationError):
            ServerConfig.parse(SERVER, require_private_key=False)


class WireGuardRuntimeTests(SimpleTestCase):
    def test_host_or_unexpected_namespace_is_rejected_before_any_mutation(self):
        with patch.dict(os.environ, {}, clear=True), patch("frontporch.vpn_runtime.command") as run:
            with self.assertRaises(VPNRuntimeError):
                verify_namespace(ServerConfig.parse(SERVER))
            run.assert_not_called()
        with patch.dict(os.environ, {"FRONTPORCH_VPN_CONTAINER": "1"}), \
                patch("frontporch.vpn_runtime.Path.is_file", return_value=True), \
                patch("frontporch.vpn_runtime.command", return_value=json.dumps([
                    {"ifname": "eth0", "addr_info": [{"local": "192.168.1.10"}]},
                ])) as run:
            with self.assertRaises(VPNRuntimeError):
                verify_namespace(ServerConfig.parse(SERVER))
            self.assertEqual(run.call_args.args[0][:4], ["ip", "-j", "-4", "address"])
            self.assertEqual(run.call_count, 1)

    def test_private_atomic_files_and_bounded_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            atomic_private_file(path, '{"value": 1}')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(read_json(path), {"value": 1})
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            atomic_private_file(path, "x" * (1024 * 1024 + 1))
            with self.assertRaises(VPNConfigurationError):
                read_json(path)

    def test_command_failure_does_not_expose_secrets_or_raw_output(self):
        import subprocess
        error = subprocess.CalledProcessError(1, ["wg"], output=SERVER_KEY, stderr=PSK)
        with patch("frontporch.vpn_runtime.subprocess.run", side_effect=error):
            with self.assertRaises(VPNRuntimeError) as ctx:
                command(["wg", "syncconf", "wg0", "/run/private"])
        self.assertNotIn(SERVER_KEY, str(ctx.exception))
        self.assertNotIn(PSK, str(ctx.exception))
