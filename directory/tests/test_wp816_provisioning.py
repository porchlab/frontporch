import base64
import threading
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from django.test import SimpleTestCase

from directory.provisioning_pilot import PilotProfile, pilot_server
from directory.wp816 import (
    WP816ConfigurationError, account_label_profile, bootstrap_profile,
    device_profile, disable_provisioning,
)


MAC = "020000000001"
PRIVATE = base64.b64encode(b"a" * 32).decode()
PUBLIC = base64.b64encode(b"b" * 32).decode()
WG = f"""[Interface]
PrivateKey = {PRIVATE}
Address = 10.77.0.2/32
MTU = 1380
[Peer]
PublicKey = {PUBLIC}
Endpoint = vpn.example.invalid:51820
AllowedIPs = 10.77.0.1/32
PersistentKeepalive = 25
"""
SIP = {
    "device_name": "Test phone & family", "sip_server": "10.77.0.1",
    "parent_extension": "123",
    "sip_port": 5060, "sip_username": "test-phone", "sip_password": "example<&>secret",
    "transport": "UDP", "nat_traversal": "WireGuard", "codec": "PCMU / G.711u",
    "dtmf": "RFC2833", "registration": True,
}


class ProfileTests(SimpleTestCase):
    def test_profile_is_mac_bound_and_credentials_round_trip_as_text(self):
        xml = device_profile(MAC, WG, SIP)
        root = ET.fromstring(xml)
        self.assertEqual(root.findtext("mac"), MAC.lower())
        self.assertEqual(root.findtext("config/P34"), SIP["sip_password"])
        self.assertEqual(root.findtext("config/P270"), "FrontPorch 123")
        self.assertNotIn(SIP["device_name"].encode(), xml)
        self.assertEqual(root.findtext("config/P22587"), PRIVATE)
        self.assertEqual(root.findtext("config/P22591"), "10.77.0.1/32")
        self.assertEqual(root.findtext("config/P52"), "5")
        self.assertEqual(root.findtext("config/P95002"), "0")
        self.assertEqual(root.findtext("config/P31"), "1")
        self.assertEqual(root.findtext("config/P22586"), "")
        self.assertEqual(device_profile(MAC, WG, SIP), xml)

    def test_sip_server_must_travel_over_vpn(self):
        for address in ("192.168.40.2", "8.8.8.8", "sip.example.invalid"):
            with self.subTest(address=address), self.assertRaises(WP816ConfigurationError):
                device_profile(MAC, WG, {**SIP, "sip_server": address})

    def test_unbounded_public_and_ipv6_routes_rejected(self):
        for routes in ("0.0.0.0/0", "8.8.8.8/32", "::/0", "10.77.0.1/32,0.0.0.0/0"):
            with self.subTest(routes=routes), self.assertRaises(WP816ConfigurationError):
                device_profile(MAC, WG.replace("AllowedIPs = 10.77.0.1/32", f"AllowedIPs = {routes}"), SIP)

    def test_hooks_duplicate_peers_bad_keys_and_malformed_config_rejected(self):
        cases = (WG + "\nPostUp = echo sensitive\n", WG + "\n[Peer]\nPublicKey = bad\n",
                 WG.replace(PRIVATE, "not-a-key"), WG.replace("[Interface]", "missing-section"))
        for config in cases:
            with self.subTest(config=cases.index(config)), self.assertRaises(WP816ConfigurationError) as ctx:
                device_profile(MAC, config, SIP)
            for secret in (PRIVATE, SIP["sip_password"], "sensitive"):
                self.assertNotIn(secret, str(ctx.exception))

    def test_invalid_endpoints_and_unsupported_sip_settings_rejected(self):
        for endpoint in ("user:secret@vpn.example.invalid:51820", "vpn.example.invalid:99999",
                         "vpn.example.invalid:51820/path", "vpn.example.invalid"):
            with self.subTest(endpoint=endpoint), self.assertRaises(WP816ConfigurationError):
                device_profile(MAC, WG.replace("vpn.example.invalid:51820", endpoint), SIP)
        for field, value in (("transport", "TLS"), ("sip_port", True), ("registration", "true"),
                             ("sip_password", "password\x00bad"), ("codec", []),
                             ("nat_traversal", {})):
            with self.subTest(field=field), self.assertRaises(WP816ConfigurationError):
                device_profile(MAC, WG, {**SIP, field: value})

    def test_bootstrap_enforces_https_identity_and_omits_device_secrets(self):
        xml = bootstrap_profile(MAC, "https://provision.example.invalid/pilot/test", "test", "temporary")
        root = ET.fromstring(xml)
        self.assertEqual(root.findtext("config/P212"), "2")
        self.assertEqual(root.findtext("config/P8463"), "1")
        self.assertEqual(root.findtext("config/P22030"), "1")
        self.assertEqual(root.findtext("config/P145"), "0")
        self.assertEqual(root.findtext("config/P1414"), "1")
        for secret in (PRIVATE, SIP["sip_password"], SIP["sip_username"]):
            self.assertNotIn(secret.encode(), xml)
        for url in ("http://example.invalid", "https://u:p@example.invalid", "https://example.invalid:8443",
                    "https://example.invalid/?token=secret", "https://example.invalid/#secret"):
            with self.subTest(url=url), self.assertRaises(WP816ConfigurationError):
                bootstrap_profile(MAC, url, "test", "temporary")

    def test_retiring_pilot_clears_download_credentials_without_changing_phone_account(self):
        root = ET.fromstring(disable_provisioning(MAC))
        self.assertEqual(root.findtext("mac"), MAC.lower())
        values = {node.tag: node.text or "" for node in root.find("config")}
        self.assertEqual(values, {"P1414": "0", "P237": "", "P1360": "", "P1361": ""})

    def test_branding_update_changes_only_label_and_never_uses_a_person_name(self):
        for extension, label in ((None, "FrontPorch"), ("", "FrontPorch"),
                                 ("123", "FrontPorch 123"), (1234, "FrontPorch 1234")):
            root = ET.fromstring(account_label_profile(MAC, extension))
            self.assertEqual({n.tag: n.text for n in root.find("config")}, {"P270": label})
        for extension in (True, [], {}, "someone", "123\n", "1234567"):
            with self.subTest(extension=extension), self.assertRaises(WP816ConfigurationError):
                account_label_profile(MAC, extension)


class PilotEndpointTests(SimpleTestCase):
    def setUp(self):
        self.now = 1000
        self.xml = device_profile(MAC, WG, SIP)
        self.profile = PilotProfile(MAC, self.xml, clock=lambda: self.now, lifetime=60)
        auth = base64.b64encode(f"{self.profile.username}:{self.profile.password}".encode()).decode()
        self.headers = {"X-Forwarded-Proto": "https", "Authorization": f"Basic {auth}"}

    def request(self, *, method="GET", path=None, headers=None):
        return self.profile.respond(method, path or self.profile.path, self.headers if headers is None else headers)

    def test_authorized_mac_only_and_no_caching(self):
        code, headers, body = self.request()
        self.assertEqual(code, 200)
        self.assertEqual(body, self.xml)
        self.assertIn("no-store", headers["Cache-Control"])
        for path in (self.profile.prefix + "/cfg020000000002.xml", self.profile.prefix + "/cfg.xml",
                     "/admin/", "/.env", self.profile.path + "?anything=1", self.profile.path + "/../.env"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path=path)[0], 404)
                self.assertEqual(self.request(path=path)[2], b"")

    def test_missing_wrong_and_non_ascii_auth_do_not_disclose_profile(self):
        for supplied in ("", "Basic invalid", "Bearer invalid", "Basic é"):
            code, headers, body = self.request(headers={**self.headers, "Authorization": supplied})
            self.assertEqual(code, 401)
            self.assertIn("WWW-Authenticate", headers)
            self.assertEqual(body, b"")

    def test_plain_http_expiry_and_unsupported_methods_deny_even_valid_auth(self):
        self.assertEqual(self.request(headers={**self.headers, "X-Forwarded-Proto": "http"})[0], 403)
        self.assertEqual(self.request(method="POST")[0], 405)
        self.now += 60
        code, _, body = self.request()
        self.assertEqual(code, 410)
        self.assertEqual(body, b"")

    def test_requests_are_rate_limited_and_window_recovers(self):
        self.profile.expires_at = 2000
        for _ in range(120):
            self.request(headers={"X-Forwarded-Proto": "https"})
        code, _, body = self.request()
        self.assertEqual(code, 429)
        self.assertEqual(body, b"")
        self.now += 60
        self.assertEqual(self.request()[0], 200)

    def test_http_adapter_serves_only_profile_and_logs_status_only(self):
        events = []
        server = pilot_server(self.profile, 0, events.append)
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            self.assertEqual(server.server_address[0], "127.0.0.1")
            request = Request(f"http://127.0.0.1:{server.server_port}{self.profile.path}", headers=self.headers)
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.read(), self.xml)
                self.assertIn("no-store", response.headers["Cache-Control"])
        finally:
            thread.join(timeout=6)
            server.server_close()
        self.assertEqual(events, [200])
