"""Networking contracts and denial cases; only fictional data and mocked HTTP."""

import hashlib
import io
import json
from http.client import BadStatusLine
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from django.core.management import call_command
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from directory.gwn import (
    GWNClient, GWNError, GWNInventoryUnavailable, GWNProtocolError,
    GWNSettings, signature,
)


MAC = "020000000001"
CONFIG = GWNSettings("test-app-id", "test-secret")
TOKEN = {"access_token": "test-token", "expires_in": 3600}
ENV = {"GWN_APP_ID": "test-app-id", "GWN_SECRET_KEY": "test-secret", "GWN_REGION": "us",
       "GWN_USERNAME": "", "GWN_PASSWORD": ""}


def response(data):
    return io.BytesIO(json.dumps(data).encode())


def ok(data):
    return response({"retCode": 0, "msg": "provider text must stay private", "data": data})


def networks(ids=(7,), pages=1, page=1):
    return {"result": [{"id": i, "networkName": "private-network-name"} for i in ids], "pages": pages, "pageNum": page}


def gateway(**changes):
    return {"mac": MAC, "networkId": 7, "apType": "GWN7062ET", "versionFirmware": "1.0.3.25",
            "status": 1, "name": "private-gateway-name", "ip": "192.0.2.8", **changes}


def devices(rows=None, pages=1, page=1):
    return {"result": [gateway()] if rows is None else rows, "totalPage": pages, "currentPage": page}


class GWNClientTests(SimpleTestCase):
    def setUp(self):
        self.opener = Mock()
        self.client = GWNClient(CONFIG, opener=self.opener, clock=lambda: 1000)

    def requests(self):
        return [c.args[0] for c in self.opener.open.call_args_list]

    def test_live_verified_auth_and_signature_contract_keep_secrets_out_of_urls(self):
        self.opener.open.side_effect = [response(TOKEN), ok(networks())]
        self.assertEqual(self.client.network_ids(), [7])
        auth, read = self.requests()
        self.assertEqual(auth.full_url, "https://www.gwn.cloud/oauth/token")
        self.assertEqual(auth.method, "POST")
        self.assertEqual(parse_qs(auth.data.decode()), {"grant_type": ["client_credentials"],
            "client_id": ["test-app-id"], "client_secret": ["test-secret"]})
        self.assertEqual(urlsplit(read.full_url).path, "/oapi/v1.0.0/network/list")
        self.assertEqual(read.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(read.data, b'{"pageNum":1,"pageSize":100}')
        canonical = "&appID=test-app-id&secretKey=test-secret&timestamp=1000000&" + hashlib.sha256(read.data).hexdigest() + "&"
        self.assertEqual(parse_qs(urlsplit(read.full_url).query), {"appID": ["test-app-id"],
            "timestamp": ["1000000"], "signature": [hashlib.sha256(canonical.encode()).hexdigest()]})
        for request in self.requests():
            self.assertNotIn("test-secret", request.full_url)
            self.assertNotIn("test-token", request.full_url)

    def test_restricted_network_password_grant_and_eu_host(self):
        client = GWNClient(GWNSettings("test-id", "test-key", region="eu", username="test-user", password="test-password"), opener=self.opener)
        self.opener.open.return_value = response(TOKEN)
        client.authenticate()
        req = self.requests()[0]
        self.assertEqual(req.full_url, "https://eu.gwn.cloud/oauth/token")
        fields = parse_qs(req.data.decode())
        self.assertEqual(fields["grant_type"], ["password"])
        self.assertEqual(fields["username"], ["test-user"])
        self.assertEqual(fields["password"], [hashlib.sha256(hashlib.md5(b"test-password").hexdigest().encode()).hexdigest()])
        self.assertNotIn(b"test-password", req.data)
        for value in ("test-id", "test-key", "test-user", "test-password"):
            self.assertNotIn(value, repr(client.config))

    def test_signature_uses_exact_utf8_body(self):
        params = {"timestamp": "1000", "appID": "test-id"}
        body = '{"search":"caf\u00e9"}'.encode()
        expected = "&appID=test-id&secretKey=test-key&timestamp=1000&" + hashlib.sha256(body).hexdigest() + "&"
        self.assertEqual(signature(params, "test-key", body), hashlib.sha256(expected.encode()).hexdigest())
        self.assertNotEqual(signature(params, "test-key", body), signature(params, "test-key", body + b" "))

    def test_cached_token_is_replaced_before_expiry(self):
        clock = Mock(return_value=1000)
        client = GWNClient(CONFIG, opener=self.opener, clock=clock)
        self.opener.open.side_effect = [response(TOKEN), ok(networks()), ok(networks()), response(TOKEN), ok(networks())]
        client.network_ids()
        clock.return_value = 4569
        client.network_ids()
        clock.return_value = 4570
        client.network_ids()
        self.assertEqual([urlsplit(r.full_url).path for r in self.requests()].count("/oauth/token"), 2)

    def test_invalid_token_lifetime_and_header_injection_are_rejected(self):
        for token in ({}, {**TOKEN, "expires_in": True}, {**TOKEN, "expires_in": 0},
                      {**TOKEN, "expires_in": "3600"}, {**TOKEN, "access_token": "token\r\nInjected: secret"}):
            with self.subTest(token=token):
                self.opener.open.return_value = response(token)
                with self.assertRaises(GWNProtocolError):
                    self.client.authenticate()

    def test_config_rejects_bad_region_partial_password_and_timeout(self):
        for changes in ({"region": "https://example.invalid"}, {"username": "only-user"},
                        {"password": "only-password"}, {"timeout": 0}, {"timeout": float("nan")}, {"timeout": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                GWNSettings("test-id", "test-key", **changes)

    @override_settings(**{**ENV, "GWN_APP_ID": "", "GWN_SECRET_KEY": "", "GDMS_CLIENT_ID": "uc-id", "GDMS_CLIENT_SECRET": "uc-secret"})
    def test_no_uc_credential_fallback(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "GWN_APP_ID and GWN_SECRET_KEY"):
            GWNSettings.from_django()

    def test_http_transport_and_json_errors_do_not_leak_or_retry(self):
        for failure in (HTTPError("https://example.invalid/?token=private-value", 401, "private-provider-text", {}, None),
                        HTTPError("private-value", 500, "private-provider-text", {}, None),
                        URLError("private-value"), TimeoutError("private-value"), BadStatusLine("private-value")):
            self.opener.reset_mock()
            self.opener.open.side_effect = failure
            with self.assertRaises(GWNError) as caught:
                self.client.authenticate()
            self.assertNotIn("private", str(caught.exception))
            self.assertTrue(caught.exception.__suppress_context__)
            self.assertEqual(self.opener.open.call_count, 1)
        self.opener.open.side_effect = None
        for raw in (b'private-not-json', b'[]', b'x' * (self.client.MAX_RESPONSE_BYTES + 1)):
            self.opener.open.return_value = io.BytesIO(raw)
            with self.assertRaises(GWNProtocolError):
                self.client.authenticate()

    def test_default_opener_blocks_even_same_host_redirects(self):
        client = GWNClient(CONFIG)
        handler = next(h for h in client.opener.handlers if hasattr(h, "redirect_request"))
        self.assertIsNone(handler.redirect_request(None, None, 302, "", {}, "https://www.gwn.cloud/other"))

    def test_read_only_route_allowlist_rejects_mutations_before_authentication(self):
        for path in ("/ap/add", "/upgrade/add", "/ap/reboot", "/ap/reset", "/router/config", "/ap/delete"):
            with self.assertRaises(ValueError):
                self.client._read(path, {})
        self.opener.open.assert_not_called()

    def test_provider_errors_and_missing_data_are_sanitized(self):
        self.client._token, self.client._token_expires = "test-token", 5000
        for result in ({"retCode": 50003, "msg": "private-provider-text"}, {"retCode": True}, {"retCode": 0}, []):
            self.opener.open.return_value = response(result)
            with self.assertRaises(GWNError) as caught:
                self.client.network_ids()
            self.assertNotIn("private-provider-text", str(caught.exception))

    def test_network_pagination_and_duplicate_or_invalid_ids(self):
        self.opener.open.side_effect = [response(TOKEN), ok(networks((7,), 2)), ok(networks((8,), 2, 2))]
        self.assertEqual(self.client.network_ids(), [7, 8])
        for data in (networks((7, 7)), networks((True,)), networks((0,)), networks(("7",)),
                     networks((), 101), networks((), True), networks((7,), 0), networks((7,), 1, 2),
                     {"result": [None], "pages": 1}):
            self.opener.open.side_effect = [ok(data)]
            with self.assertRaises(GWNProtocolError):
                self.client.network_ids()

    def test_empty_network_list_and_no_inventory_envelope_are_distinct(self):
        self.opener.open.side_effect = [response(TOKEN), ok(networks((), 0)), ok("")]
        self.assertEqual(self.client.network_ids(), [])
        with self.assertRaises(GWNInventoryUnavailable):
            self.client.device(MAC, 7)

    def test_device_lookup_checks_all_pages_and_preserves_offline_or_unknown(self):
        self.opener.open.side_effect = [response(TOKEN), ok(devices([gateway(mac="020000000002")], 2)),
                                      ok(devices([gateway(status=0)], 2, 2))]
        device = self.client.device("02:00:00:00:00:01", 7)
        self.assertEqual(device.mac, MAC)
        self.assertFalse(device.online)
        self.assertNotIn(MAC, repr(device))
        for status in (1, 2):
            self.opener.open.side_effect = [ok(devices([gateway(status=status)]))]
            self.assertIs(self.client.device(MAC, 7).online, True if status == 1 else None)
        self.opener.open.side_effect = [ok(devices([], 0))]
        self.assertIsNone(self.client.device(MAC, 7))

    def test_wrong_network_model_malformed_or_duplicate_devices_fail_closed(self):
        self.client._token, self.client._token_expires = "test-token", 5000
        for rows in ([gateway(networkId=8)], [gateway(networkId=True)], [gateway(apType="GWN7062E")],
                     [gateway(mac=None)], [gateway(status=True)], [gateway(versionFirmware="private-token")],
                     [gateway(), gateway()]):
            self.opener.open.side_effect = [ok(devices(rows))]
            with self.assertRaises(GWNProtocolError):
                self.client.device(MAC, 7)
        self.opener.open.side_effect = [ok(devices(pages=2)), ok(devices(pages=2, page=2))]
        with self.assertRaises(GWNProtocolError):
            self.client.device(MAC, 7)

    def test_recommendation_requires_matching_model_and_unique_identity(self):
        self.opener.open.side_effect = [response(TOKEN), ok(devices()), ok({"result": [
            {"mac": MAC, "type": "GWN7062ET", "lastVersion": "1.0.3.25"}]})]
        device = self.client.device(MAC, 7)
        self.assertEqual(self.client.recommended_firmware(device), "1.0.3.25")
        row = {"mac": MAC, "type": "GWN7062ET", "lastVersion": "1.0.3.25"}
        for rows in ([{**row, "type": "WP816"}], [row, row], [{**row, "mac": None}],
                     [{**row, "lastVersion": "private-provider-text"}]):
            self.opener.open.side_effect = [ok({"result": rows})]
            with self.assertRaises(GWNProtocolError):
                self.client.recommended_firmware(device)
        self.opener.open.side_effect = [ok({"result": []})]
        self.assertEqual(self.client.recommended_firmware(device), "")


@override_settings(**ENV)
class CheckGWNTests(SimpleTestCase):
    def run_check(self, replies, **options):
        opener, out = Mock(), io.StringIO()
        opener.open.side_effect = [response(TOKEN), *replies]
        with patch("directory.gwn.build_opener", return_value=opener):
            call_command("check_gwn", stdout=out, **options)
        return out.getvalue(), [c.args[0] for c in opener.open.call_args_list]

    def test_default_check_only_authenticates_and_lists_network_ids(self):
        output, requests = self.run_check([ok(networks())])
        self.assertIn("Accessible network IDs: 7", output)
        self.assertEqual(len(requests), 2)
        self.assertNotIn("private-network-name", output)

    def test_operator_output_excludes_inventory_secrets_and_does_not_claim_readiness(self):
        output, requests = self.run_check([ok(networks()), ok(devices([gateway(status=0)])), ok({"result": [
            {"mac": MAC, "type": "GWN7062ET", "lastVersion": "1.0.3.25"}]})], network_id=7, mac=MAC)
        self.assertIn("cloud status: offline", output)
        self.assertIn("does not establish VPN, SIP, or audio readiness", output)
        self.assertIn("not a reviewed FrontPorch firmware target", output)
        for value in (MAC, "test-token", "test-app-id", "test-secret", "private", "192.0.2.8"):
            self.assertNotIn(value, output)
        self.assertTrue(all(urlsplit(r.full_url).path in {"/oauth/token", "/oapi/v1.0.0/network/list",
            "/oapi/v1.0.0/ap/list", "/oapi/v1.0.0/upgrade/version"} for r in requests))

    def test_inaccessible_network_is_rejected_before_device_request(self):
        with self.assertRaisesMessage(CommandError, "not accessible"):
            self.run_check([ok(networks())], network_id=8, mac=MAC)

    def test_missing_gateway_does_not_imply_available_claim(self):
        output, requests = self.run_check([ok(networks()), ok(devices([], 0))], network_id=7, mac=MAC)
        self.assertIn("does not establish claim availability", output)
        self.assertEqual(len(requests), 3)

    def test_unavailable_inventory_remains_an_error(self):
        with self.assertRaisesMessage(CommandError, "identity remains unverified"):
            self.run_check([ok(networks()), ok("")], network_id=7, mac=MAC)

    def test_invalid_input_does_not_contact_provider(self):
        for options in ({"mac": MAC}, {"network_id": 0}, {"network_id": 7, "mac": "not-a-mac"}):
            with patch("directory.gwn.build_opener") as opener, self.assertRaises(CommandError):
                call_command("check_gwn", **options)
            opener.assert_not_called()
