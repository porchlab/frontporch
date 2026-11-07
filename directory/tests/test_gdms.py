"""GDMS contract/security tests use synthetic identities and no live network."""

import hashlib
import io
import json
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from directory.gdms import (
    GDMSAPIError, GDMSClient, GDMSError, GDMSProtocolError, GDMSSettings,
    GDMSTransportError, _NoRedirects, normalize_mac, signature,
)


MAC = "020000000001"
CONFIG = GDMSSettings("test-user", "test-password", "test-id", "test-secret")


def response(data):
    return io.BytesIO(json.dumps(data).encode())


def ok(data):
    return response({"retCode": 0, "msg": "", "data": data})


class GDMSClientTests(SimpleTestCase):
    def setUp(self):
        self.opener = Mock()
        self.client = GDMSClient(CONFIG, opener=self.opener, clock=lambda: 1000)
        self.token = {"access_token": "test-token", "expires_in": 3600}

    def requests(self):
        return [c.args[0] for c in self.opener.open.call_args_list]

    def test_live_details_require_followup_and_matching_identity(self):
        live = {"device": {"mac": MAC, "softwareVersion": "1.0.3.39"}}
        self.opener.open.side_effect = [response(self.token), ok(live), ok(live), ok({"device": {"mac": "020000000002"}})]
        self.assertIsNone(self.client.live_device(MAC, first=True))
        self.assertEqual(self.client.live_device(MAC, first=False)["softwareVersion"], "1.0.3.39")
        with self.assertRaises(GDMSProtocolError):
            self.client.live_device(MAC, first=False)
        request = self.requests()[1]
        self.assertEqual(urlsplit(request.full_url).path, "/oapi/v1.0.0/device/detail")
        self.assertEqual(json.loads(request.data)["isFirst"], 1)
        self.assertEqual(json.loads(self.requests()[2].data)["isFirst"], 0)

    def test_login_uses_post_and_hashes_locally(self):
        self.opener.open.return_value = response(self.token)
        self.client.authenticate()
        req = self.requests()[0]
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.full_url, "https://www.gdms.cloud/oapi/oauth/token")
        fields = parse_qs(req.data.decode())
        expected = hashlib.sha256(hashlib.md5(b"test-password").hexdigest().encode()).hexdigest()
        self.assertEqual(fields["password"], [expected])
        self.assertNotIn(b"test-password", req.data)
        for secret in ("test-user", "test-password", "test-id", "test-secret"):
            self.assertNotIn(secret, repr(CONFIG))

    def test_signature_uses_sorted_raw_params_and_exact_body_bytes(self):
        params = {"timestamp": "1000000", "access_token": "test-token", "search": "a b"}
        body = b'{"name":"example"}'
        canonical = (
            "&access_token=test-token&client_id=test-id&client_secret=test-secret"
            "&search=a b&timestamp=1000000&" + hashlib.sha256(body).hexdigest() + "&"
        )
        self.assertEqual(signature(params, "test-id", "test-secret", body),
                         hashlib.sha256(canonical.encode()).hexdigest())
        self.assertNotEqual(signature(params, "test-id", "test-secret", body),
                            signature(params, "test-id", "test-secret", body + b"\n"))
        self.assertNotIn("client_secret", params)

    def test_organization_pagination_and_token_reuse(self):
        self.opener.open.side_effect = [response(self.token),
            ok({"result": [{"id": 1}], "pages": 2}), ok({"result": [{"id": 2}], "pages": 2})]
        self.assertEqual(self.client.organizations(), [{"id": 1}, {"id": 2}])
        self.assertEqual(len(self.requests()), 3)
        req = self.requests()[2]
        self.assertEqual(req.method, "GET")
        self.assertEqual(parse_qs(urlsplit(req.full_url).query)["pageNum"], ["2"])
        self.assertNotIn("test-secret", req.full_url)

    def test_expired_token_is_reauthenticated(self):
        self.opener.open.side_effect = [response(self.token), response(self.token)]
        self.client.authenticate()
        self.client.clock = lambda: 5000
        self.opener.open.side_effect = [response(self.token), ok({"result": []})]
        self.client.sites(1)
        self.assertEqual(self.requests()[1].full_url, "https://www.gdms.cloud/oapi/oauth/token")

    def test_eu_host_and_invalid_configuration(self):
        self.assertEqual(GDMSSettings("u", "p", "i", "s", region="eu").base_url,
                         "https://eu.gdms.cloud/oapi")
        for kwargs in ({"region": "attacker.example"}, {"timeout": 0}, {"timeout": 61}):
            with self.assertRaises(ValueError):
                GDMSSettings("u", "p", "i", "s", **kwargs)

    def test_add_device_checks_partial_batch_failure(self):
        self.opener.open.side_effect = [response(self.token), ok({
            "total": 1, "success": 0, "failure": 1,
            "errorDeviceList": [{"errorMsg": "sensitive provider message"}],
        })]
        with self.assertRaises(GDMSError) as ctx:
            self.client.add_device(mac=MAC, serial="TEST001", device_name="fp-1", org_id=1, site_id=2)
        self.assertNotIn("sensitive", str(ctx.exception))
        req = self.requests()[1]
        self.assertEqual(json.loads(req.data), [{"mac": "02:00:00:00:00:01", "sn": "TEST001",
            "deviceName": "fp-1", "orgId": 1, "siteId": 2}])
        params = {k: v[0] for k, v in parse_qs(urlsplit(req.full_url).query).items()}
        actual = params.pop("signature")
        self.assertEqual(actual, signature(params, CONFIG.client_id, CONFIG.client_secret, req.data))

    def test_successful_add(self):
        self.opener.open.side_effect = [response(self.token), ok({
            "total": 1, "success": 1, "failure": 0, "errorDeviceList": [],
        })]
        self.client.add_device(mac=MAC, serial="TEST001", device_name="fp-1", org_id=1, site_id=2)

    def test_device_lookup_rejects_other_organization(self):
        self.opener.open.side_effect = [response(self.token), ok({"result": [{"mac": MAC, "orgId": 2}]})]
        with self.assertRaises(GDMSProtocolError):
            self.client.device(MAC, 1)

    def test_device_lookup_requires_exact_mac(self):
        self.opener.open.side_effect = [response(self.token), ok({"result": [{"mac": "020000000002", "orgId": 1}]})]
        self.assertIsNone(self.client.device(MAC, 1))

    def test_firmware_task_is_not_assumed_complete(self):
        self.opener.open.side_effect = [response(self.token), ok({"taskId": 42})]
        task = self.client.upgrade(mac=MAC, org_id=1, task_name="fp-1-upgrade-1",
                                   firmware_url="https://firmware.example.invalid/wp816.bin")
        self.assertEqual(task, 42)
        body = json.loads(self.requests()[1].data)
        self.assertEqual(body["taskType"], 3)
        self.assertEqual(body["macList"], ["02:00:00:00:00:01"])
        self.assertEqual(body["execType"], 1)

    def test_xml_is_signed_as_file_digest_and_multipart_body(self):
        self.opener.open.side_effect = [response(self.token), ok("")]
        xml = b'<?xml version="1.0"?><gs_provision version="1"><config version="1"><P237>example.invalid</P237></config></gs_provision>'
        self.client.configure_xml(mac=MAC, org_id=1, xml=xml)
        req = self.requests()[1]
        self.assertIn("multipart/form-data; boundary=", req.get_header("Content-type"))
        self.assertIn(xml, req.data)
        self.assertIn(b'name="xml"; filename="config.xml"', req.data)
        params = {k: v[0] for k, v in parse_qs(urlsplit(req.full_url).query).items()}
        actual = params.pop("signature")
        params.update(mac="02:00:00:00:00:01", orgId="1", applyConfig="true",
                      xml=hashlib.md5(xml).hexdigest())
        self.assertEqual(actual, signature(params, CONFIG.client_id, CONFIG.client_secret))

    def test_transport_errors_hide_signed_urls_and_are_not_retried(self):
        for error in (URLError("https://secret-token.invalid"),
                      HTTPError("https://secret-token.invalid", 401, "secret-message", {}, None)):
            self.opener.reset_mock()
            self.client._token = "test-token"
            self.client._token_expires = 5000
            self.opener.open.side_effect = error
            with self.assertRaises(GDMSTransportError) as ctx:
                self.client.upgrade(mac=MAC, org_id=1, task_name="fp-1",
                                    firmware_url="https://example.invalid/fw.bin")
            self.assertNotIn("secret", str(ctx.exception))
            self.assertTrue(ctx.exception.__suppress_context__)
            self.assertEqual(self.opener.open.call_count, 1)

    def test_redirects_are_not_followed(self):
        self.assertIsNone(_NoRedirects().redirect_request(None, None, 302, "", {}, "https://other.invalid"))

    def test_errors_and_invalid_responses_are_sanitized(self):
        for payload in ([1], {"msg": "secret"}, {"retCode": True, "data": {}},
                        {"retCode": 0}, {"retCode": 50007, "msg": "secret"}):
            self.client._token = "test-token"
            self.client._token_expires = 5000
            self.opener.open.return_value = response(payload)
            with self.assertRaises(GDMSError) as ctx:
                self.client.sites(1)
            self.assertNotIn("secret", str(ctx.exception))

    def test_oversized_and_non_json_response(self):
        self.client._token = "test-token"
        self.client._token_expires = 5000
        for payload in (b"x" * (GDMSClient.MAX_RESPONSE_BYTES + 1), b"not-json", b"\xff"):
            self.opener.open.return_value = io.BytesIO(payload)
            with self.assertRaises(GDMSProtocolError):
                self.client.sites(1)

    def test_invalid_inputs_never_reach_network(self):
        for value in ("invalid", "00:11-22:33:44:55", "001122334455/path"):
            with self.assertRaises(ValueError):
                self.client.device(value, 1)
        for url in ("http://example.invalid/fw", "https://u:p@example.invalid/fw", "https:///fw"):
            with self.assertRaises(ValueError):
                self.client.upgrade(mac=MAC, org_id=1, task_name="fp-1", firmware_url=url)
        self.opener.open.assert_not_called()

    def test_mac_normalization(self):
        self.assertEqual(normalize_mac("02:00:00:00:00:ab"), "0200000000AB")
        self.assertEqual(normalize_mac("02-00-00-00-00-ab"), "0200000000AB")


@override_settings(GDMS_USERNAME="u", GDMS_PASSWORD="p", GDMS_CLIENT_ID="i", GDMS_CLIENT_SECRET="s")
class GDMSCommandTests(SimpleTestCase):
    @patch("directory.management.commands.check_gdms.GDMSClient")
    def test_read_only_check_redacts_device_and_account_metadata(self, factory):
        client = factory.return_value
        client.organizations.return_value = [{"id": 1, "organization": "Private family"}]
        client.sites.return_value = [{"id": 2, "children": [{"id": 3}]}]
        client.device.return_value = {"deviceType": "WP816", "firmwareVersion": "1.0.0.1",
                                      "status": 1, "sn": "PRIVATE-SERIAL", "privateip": "PRIVATE-IP"}
        output = io.StringIO()
        call_command("check_gdms", org_id=1, site_id=3, mac=MAC, stdout=output)
        self.assertIn("WP816", output.getvalue())
        self.assertIn("No devices were changed", output.getvalue())
        for secret in (MAC, "PRIVATE-SERIAL", "PRIVATE-IP", "Private family"):
            self.assertNotIn(secret, output.getvalue())
        self.assertEqual([call[0] for call in client.method_calls], ["organizations", "sites", "device"])

    @patch("directory.management.commands.check_gdms.GDMSClient")
    def test_foreign_site_is_rejected_before_device_lookup(self, factory):
        client = factory.return_value
        client.organizations.return_value = [{"id": 1}]
        client.sites.return_value = [{"id": 2}]
        with self.assertRaises(CommandError):
            call_command("check_gdms", org_id=1, site_id=3, mac=MAC, stdout=io.StringIO())
        client.device.assert_not_called()

    @override_settings(GDMS_USERNAME="", GDMS_PASSWORD="", GDMS_CLIENT_ID="", GDMS_CLIENT_SECRET="")
    def test_missing_credentials_reports_names_only(self):
        with self.assertRaisesMessage(CommandError, "GDMS_USERNAME"):
            call_command("check_gdms")

    def test_mac_requires_explicit_organization(self):
        with self.assertRaisesMessage(CommandError, "require --org-id"):
            call_command("check_gdms", mac=MAC)
