import base64
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from directory.enrollment_worker import EnrollmentWorker, allocate_phone, credentials, publish_profile, profile_path, TARGET_FIRMWARE
from directory.gdms import GDMSTransportError, GDMSAPIError
from directory.models import Child, Device, Family, Parent, PhoneEnrollment, PhoneEnrollmentOperation, PhoneEnrollmentState as State, WireGuardPeer
from frontporch.phone_profiles import ProfileApplication


@override_settings(PHONE_ENROLLMENT_ENABLED=True, ASTERISK_AUTO_APPLY_CONFIG=False)
class EnrollmentTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="River House")
        self.user = User.objects.create_user(username="river", password="test-password")
        self.parent = Parent.objects.create(user=self.user, family=self.family, display_name="Morgan")
        self.child = Child.objects.create(family=self.family, name="Rowan")
        self.other = Family.objects.create(name="Hill House")
        self.other_user = User.objects.create_user(username="hill", password="test-password")
        self.other_parent = Parent.objects.create(user=self.other_user, family=self.other, display_name="Alex")
        self.client.force_login(self.user)
        self.data = {"person": f"parent:{self.parent.pk}", "friendly_name": "Kitchen phone", "mac": "02:00:00:00:00:01", "serial": "TEST00000001", "possession": "on"}
        self.url = reverse("directory:phone_setup_register")

    def register(self):
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 302)
        return PhoneEnrollment.objects.get()

    def test_parent_registers_for_parent_child_or_household_without_secrets_or_remote_calls(self):
        with patch("directory.gdms.GDMSClient._request") as remote, override_settings(WIREGUARD_ENCRYPTION_KEY=""):
            enrollment = self.register()
        remote.assert_not_called()
        self.assertEqual(enrollment.assigned_parent, self.parent)
        self.assertEqual(enrollment.family, self.family)
        self.assertEqual(enrollment.mac, "020000000001")
        self.assertFalse(Device.objects.exists())
        self.assertFalse(WireGuardPeer.objects.exists())
        self.assertTrue(self.family.activity.filter(description__contains="Started phone setup").exists())
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PhoneEnrollment.objects.count(), 1)
        self.data.update(person=f"child:{self.child.pk}", mac="020000000002", serial="TEST00000002")
        self.client.post(self.url, self.data)
        self.assertEqual(PhoneEnrollment.objects.get(mac="020000000002").assigned_child, self.child)
        self.data.update(person="family", mac="020000000003", serial="TEST00000003")
        self.client.post(self.url, self.data)
        self.assertIsNone(PhoneEnrollment.objects.get(mac="020000000003").assigned_child_id)

    def test_foreign_family_person_and_injected_state_are_not_accepted(self):
        response = self.client.post(self.url, {**self.data, "person": f"parent:{self.other_parent.pk}", "family": self.other.pk, "state": "ready", "org_id": 9000})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PhoneEnrollment.objects.exists())

    def test_registration_csrf_login_guardian_and_feature_gate(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(self.url, self.data).status_code, 403)
        self.parent.is_guardian = False
        self.parent.save()
        self.assertEqual(self.client.post(self.url, self.data).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.other_user)
        with override_settings(PHONE_ENROLLMENT_ENABLED=False):
            self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_ownership_duplicate_and_status_do_not_disclose_another_family(self):
        enrollment = self.register()
        self.client.force_login(self.other_user)
        for name in ("phone_setup_detail", "phone_setup_progress"):
            self.assertEqual(self.client.get(reverse("directory:" + name, args=[enrollment.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("directory:phone_setup_check", args=[enrollment.pk])).status_code, 404)
        response = self.client.post(self.url, {**self.data, "person": f"parent:{self.other_parent.pk}"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.family.name)
        self.assertNotContains(response, str(enrollment.pk))
        self.assertEqual(PhoneEnrollment.objects.count(), 1)

    def test_progress_is_private_minimal_and_get_cannot_trigger_work(self):
        enrollment = self.register()
        with patch("directory.gdms.GDMSClient._request") as remote:
            response = self.client.get(reverse("directory:phone_setup_progress", args=[enrollment.pk]))
        remote.assert_not_called()
        self.assertIn("no-store", response["Cache-Control"])
        for secret in (enrollment.mac, enrollment.serial, "sip_secret", "encrypted_bootstrap", "org_id"):
            self.assertNotIn(secret, response.content.decode())
        self.assertEqual(self.client.get(reverse("directory:phone_setup_check", args=[enrollment.pk])).status_code, 405)

    def test_repeated_submit_cannot_change_owner(self):
        enrollment = self.register()
        self.client.post(self.url, {**self.data, "person": f"child:{self.child.pk}"})
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.assigned_parent, self.parent)


@override_settings(PHONE_ENROLLMENT_ENABLED=True, ASTERISK_AUTO_APPLY_CONFIG=False,
    GDMS_ORG_ID="1", GDMS_SITE_ID="2", WIREGUARD_SERVER_ADDRESS="10.77.0.1/24",
    WIREGUARD_SERVER_PUBLIC_KEY=base64.b64encode(b"s" * 32).decode(),
    WIREGUARD_ENDPOINT="vpn.example.com:51820", PHONE_PROFILE_PUBLIC_URL="https://phones.example.com/phone-profiles",
    WP816_FIRMWARE_URL="https://firmware.grandstream.com/wp8x6fw.bin")
class EnrollmentWorkerTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "profiles").mkdir(); (root / "receipts").mkdir()
        self.config = override_settings(PHONE_PROFILE_DIR=str(root / "profiles"), PHONE_RECEIPT_DIR=str(root / "receipts"), WIREGUARD_ENCRYPTION_KEY=Fernet.generate_key().decode())
        self.config.enable(); self.addCleanup(self.config.disable)
        self.family = Family.objects.create(name="River House")
        self.parent = Parent.objects.create(user=User.objects.create_user(username="guardian"), family=self.family, display_name="Morgan")
        self.enrollment = PhoneEnrollment.objects.create(family=self.family, requested_by=self.parent, assigned_parent=self.parent,
            mac="020000000001", serial="TEST00000001", friendly_name="Kitchen phone")
        self.now = timezone.now()
        self.client = Mock()
        self.contact = Mock(return_value=False)
        self.apply = Mock()
        self.worker = EnrollmentWorker(self.client, clock=lambda: self.now, contact_check=self.contact, apply=self.apply)
        self.row = {"mac": self.enrollment.mac, "sn": self.enrollment.serial, "deviceName": self.enrollment.provider_name, "orgId": 1, "siteId": 2, "deviceType": "WP816", "status": 1}
        self.client.device.return_value = None

    def tick(self, seconds=15):
        self.now += timedelta(seconds=seconds)
        self.enrollment.refresh_from_db()
        self.worker.step(self.enrollment)
        self.enrollment.refresh_from_db()

    def enrolled(self):
        self.tick()
        self.client.device.return_value = self.row
        self.tick()
        self.assertEqual(self.enrollment.state, State.WIFI)

    def verified(self):
        self.enrolled()
        self.client.live_device.side_effect = [None, {"mac": self.enrollment.mac, "sn": self.enrollment.serial, "softwareVersion": TARGET_FIRMWARE}]
        self.tick(); self.tick()
        self.assertEqual(self.enrollment.state, State.CONFIGURING)

    def configured(self):
        self.verified(); self.tick()
        self.assertEqual(self.enrollment.state, State.CONNECTING)

    def test_restart_after_lost_add_response_reconciles_without_repeating(self):
        self.client.add_device.side_effect = GDMSTransportError("outcome unknown")
        with self.assertRaises(GDMSTransportError): self.tick()
        self.assertEqual(self.enrollment.operations.get(kind="add").status, "started")
        self.tick()
        self.client.add_device.assert_called_once()
        self.client.device.return_value = self.row
        self.tick()
        self.assertEqual(self.enrollment.state, State.WIFI)
        self.assertFalse(Device.objects.exists())

    def test_preexisting_provider_device_is_never_adopted(self):
        self.client.device.return_value = self.row
        self.tick()
        self.assertEqual(self.enrollment.problem, "ownership")
        self.client.add_device.assert_not_called()
        self.client.configure_xml.assert_not_called()

    def test_firmware_gate_ignores_inventory_version_and_first_live_response(self):
        self.enrolled()
        self.row["firmwareVersion"] = TARGET_FIRMWARE
        self.client.live_device.return_value = None
        self.tick(); self.tick()
        self.assertFalse(Device.objects.exists())
        self.client.configure_xml.assert_not_called()
        self.assertIsNone(self.enrollment.firmware_verified_at)

    @patch("directory.enrollment_worker.verify_firmware_download")
    def test_upgrade_queues_once_and_waits_for_fresh_version(self, download):
        self.enrolled()
        self.client.live_device.return_value = {"mac": self.enrollment.mac, "sn": self.enrollment.serial, "softwareVersion": "1.0.1.18"}
        self.client.upgrade.return_value = 101
        for _ in range(6): self.tick()
        self.client.upgrade.assert_called_once()
        download.assert_called_once()
        self.client.configure_xml.assert_not_called()
        self.assertFalse(Device.objects.exists())
        self.client.live_device.return_value["softwareVersion"] = TARGET_FIRMWARE
        self.tick(); self.tick(); self.tick()
        self.assertEqual(self.enrollment.state, State.CONNECTING)

    def test_newer_or_wrong_serial_firmware_is_not_downgraded_or_configured(self):
        self.enrolled()
        self.client.live_device.return_value = {"sn": self.enrollment.serial, "softwareVersion": "1.0.4.1"}
        self.tick(); self.tick()
        self.assertEqual(self.enrollment.problem, "firmware")
        self.client.upgrade.assert_not_called()
        self.client.configure_xml.assert_not_called()

    def test_profile_uses_new_family_peer_and_parent_extension_and_no_person_name_to_gdms(self):
        self.configured()
        device = self.enrollment.device
        self.assertEqual(device.assigned_parent, self.parent)
        self.assertEqual(device.sip_extension, self.parent.dial_extension)
        self.assertEqual(device.wireguard_peer.family, self.family)
        self.assertEqual(device.wireguard_peer.provisioning_method, "gdms")
        xml = self.client.configure_xml.call_args.kwargs["xml"].decode()
        self.assertNotIn(device.sip_secret, xml)
        self.assertNotIn("Morgan", xml)
        self.assertNotIn("River", xml)
        lease = json.loads(profile_path(self.enrollment).read_text())
        profile = base64.b64decode(lease["xml"]).decode()
        self.assertIn("FrontPorch " + self.parent.dial_extension, profile)
        self.assertIn(device.sip_secret, profile)
        self.assertNotIn("Morgan", profile)
        self.apply.assert_called_once_with(reload=True)

    def test_interrupted_pbx_apply_resumes_without_duplicate_peer_or_device(self):
        self.verified()
        self.apply.side_effect = OSError("pbx unavailable")
        with self.assertRaises(OSError): self.tick()
        self.assertEqual(Device.objects.count(), 1)
        self.assertEqual(WireGuardPeer.objects.count(), 1)
        self.client.configure_xml.assert_not_called()
        self.apply.side_effect = None
        self.tick()
        self.assertEqual(Device.objects.count(), 1)
        self.assertEqual(self.enrollment.state, State.CONNECTING)

    def test_bootstrap_lost_response_is_not_resent_or_reported_ready(self):
        self.verified()
        self.client.configure_xml.side_effect = GDMSTransportError("unknown")
        with self.assertRaises(GDMSTransportError): self.tick()
        self.tick(); self.tick()
        self.client.configure_xml.assert_called_once()
        self.assertEqual(self.enrollment.state, State.CONNECTING)

    def test_ready_requires_download_fresh_handshake_and_contact_then_revokes_profile(self):
        self.configured()
        self.contact.return_value = True
        peer = self.enrollment.device.wireguard_peer
        WireGuardPeer.objects.filter(pk=peer.pk).update(last_handshake_at=self.now)
        self.tick()
        self.assertEqual(self.enrollment.state, State.CONNECTING)
        receipt = Path(settings.PHONE_RECEIPT_DIR) / (self.enrollment.pk.hex + ".json")
        receipt.write_text(json.dumps({"id": self.enrollment.pk.hex, "at": self.now.timestamp()}))
        WireGuardPeer.objects.filter(pk=peer.pk).update(last_handshake_at=self.now - timedelta(minutes=10))
        self.tick()
        self.assertEqual(self.enrollment.state, State.CONNECTING)
        WireGuardPeer.objects.filter(pk=peer.pk).update(last_handshake_at=self.now)
        self.contact.return_value = False
        self.tick()
        self.assertEqual(self.enrollment.state, State.CONNECTING)
        self.contact.return_value = True
        self.tick()
        self.assertEqual(self.enrollment.state, State.READY)
        self.assertFalse(profile_path(self.enrollment).exists())
        self.assertEqual(self.enrollment.encrypted_bootstrap, "")
        self.assertTrue(self.enrollment.operations.filter(kind="retire").exists())

    def test_expired_delivery_and_revoked_guardian_revoke_profile(self):
        self.configured()
        self.tick(seconds=3601)
        self.assertEqual(self.enrollment.problem, "delivery_timeout")
        self.assertFalse(profile_path(self.enrollment).exists())

    def test_revoked_actor_prevents_all_provider_calls(self):
        self.parent.is_guardian = False; self.parent.save()
        self.tick()
        self.assertEqual(self.enrollment.problem, "access")
        self.client.device.assert_not_called()

    def test_stale_verification_does_not_release_profile(self):
        self.verified()
        self.tick(seconds=121)
        self.assertEqual(self.enrollment.state, State.FIRMWARE)
        self.assertFalse(Device.objects.exists())

    def test_wrong_model_stops_before_any_phone_settings(self):
        self.tick()
        self.row["deviceType"] = "WP820"
        self.client.device.return_value = self.row
        self.tick()
        self.assertEqual(self.enrollment.problem, "model")
        self.client.configure_xml.assert_not_called()

    def test_command_persists_retries_without_logging_provider_secrets(self):
        import io
        from django.core.management import call_command
        from directory.management.commands import provision_phones
        output = io.StringIO()
        failed = Mock()
        failed.step.side_effect = RuntimeError("provider-token-must-not-leak")
        with patch.object(provision_phones, "validate_configuration"), patch.object(provision_phones, "EnrollmentWorker", return_value=failed), patch.object(provision_phones, "close_old_connections"):
            for _ in range(3):
                PhoneEnrollment.objects.filter(pk=self.enrollment.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
                call_command("provision_phones", once=True, stderr=output, stdout=output)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.consecutive_failures, 3)
        self.assertEqual(self.enrollment.problem, "service")
        self.assertEqual(self.enrollment.state, State.QUEUED)
        self.assertNotIn("provider-token", output.getvalue())
        self.assertTrue((Path(settings.PHONE_PROFILE_DIR) / "worker-health.json").exists())

    def test_profile_endpoint_requires_matching_path_auth_tls_and_live_lease(self):
        self.configured()
        auth = credentials(self.enrollment)
        app = ProfileApplication(settings.PHONE_PROFILE_DIR, settings.PHONE_RECEIPT_DIR, clock=lambda: self.now.timestamp())
        path = f"/phone-profiles/{self.enrollment.pk.hex}/cfg{self.enrollment.mac.lower()}.xml"
        basic = "Basic " + base64.b64encode(f"{auth['username']}:{auth['password']}".encode()).decode()
        def request(**changes):
            response = []
            body = b"".join(app({"PATH_INFO": path, "REQUEST_METHOD": "GET", "HTTP_X_FORWARDED_PROTO": "https", "HTTP_AUTHORIZATION": basic, **changes}, lambda status, headers: response.extend([status, dict(headers)])))
            return response[0], response[1], body
        for overrides in ({"HTTP_AUTHORIZATION": ""}, {"HTTP_AUTHORIZATION": "Basic bad!"}, {"HTTP_X_FORWARDED_PROTO": "http"}, {"REQUEST_METHOD": "POST"}, {"PATH_INFO": "/admin/"}, {"QUERY_STRING": "token=other"}, {"PATH_INFO": path.replace("000001", "000002")}):
            status, headers, body = request(**overrides)
            self.assertNotEqual(status, "200 OK"); self.assertEqual(body, b"")
        status, headers, body = request()
        self.assertEqual(status, "200 OK")
        self.assertIn("no-store", headers["Cache-Control"])
        self.assertIn(b"gs_provision", body)
        self.assertTrue((Path(settings.PHONE_RECEIPT_DIR) / (self.enrollment.pk.hex + ".json")).exists())
        self.now += timedelta(seconds=3601)
        self.assertNotEqual(request()[0], "200 OK")


class ContactObservationTests(SimpleTestCase):
    @patch("directory.enrollment_worker.AsteriskManagerClient")
    def test_contact_match_requires_exact_account_and_available_status(self, client):
        from directory.enrollment_worker import contacts_available
        output = Mock()
        client.return_value.run_cli_commands.return_value = [output]
        for line, expected in (
            (" Contact: phone-abc/sip:phone-abc@10.77.1.1:42000 012345abcd Avail 8.3", True),
            (" Contact: phone-abcd/sip:phone-abcd@10.77.1.1:42000 012345abcd Avail 8.3", False),
            (" Contact: phone-abc/sip:phone-abc@10.77.1.1:42000 012345abcd Unavail nan", False),
            ("Objects found: 0", False),
        ):
            output.output = line
            self.assertEqual(contacts_available("phone-abc"), expected)
        client.return_value.run_cli_commands.assert_called_with(("pjsip show contacts",))
