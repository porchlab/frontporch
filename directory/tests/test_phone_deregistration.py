import base64
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from directory.asterisk.builder import build_asterisk_configuration
from directory.enrollment_worker import EnrollmentWorker, allocate_phone, profile_path
from directory.gdms import GDMSTransportError, GDMSAPIError
from directory.models import (
    Child, Device, DialShortcut, Family, Parent, PhoneEnrollment,
    PhoneEnrollmentOperation, PhoneEnrollmentState as State, WireGuardPeer,
)


@override_settings(PHONE_ENROLLMENT_ENABLED=True, ASTERISK_AUTO_APPLY_CONFIG=False,
    WIREGUARD_SERVER_ADDRESS="10.77.0.1/24",
    WIREGUARD_SERVER_PUBLIC_KEY=base64.b64encode(b"s" * 32).decode(),
    WIREGUARD_ENDPOINT="vpn.example.com:51820")
class DeregistrationFixture(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = override_settings(
            PHONE_PROFILE_DIR=self.temp.name, PHONE_RECEIPT_DIR=self.temp.name,
            WIREGUARD_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        )
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.family = Family.objects.create(name="River House")
        self.user = User.objects.create_user(username="river")
        self.parent = Parent.objects.create(user=self.user, family=self.family, display_name="Morgan")
        self.child = Child.objects.create(family=self.family, name="Rowan")
        self.enrollment = PhoneEnrollment.objects.create(
            family=self.family, requested_by=self.parent, assigned_child=self.child,
            mac="020000000001", serial="TEST00000001", friendly_name="Bedroom",
            state=State.READY, org_id=1, site_id=2, gdms_added_at=timezone.now(),
        )
        allocate_phone(self.enrollment)
        self.device_id = self.enrollment.device_id
        self.username = self.enrollment.device.sip_username
        self.secret = self.enrollment.device.sip_secret
        self.peer_id = self.enrollment.device.wireguard_peer_id
        self.url = reverse("directory:phone_deregister", args=[self.enrollment.pk])
        self.confirm_url = reverse("directory:phone_confirm_reset", args=[self.enrollment.pk])
        self.detail_url = reverse("directory:phone_setup_detail", args=[self.enrollment.pk])
        self.client.force_login(self.user)

    def request_removal(self):
        self.client.post(self.url, {"confirm": "on"})
        self.enrollment.refresh_from_db()


class DeregistrationViewTests(DeregistrationFixture):
    def test_confirmation_and_duplicate_submissions_only_record_intent(self):
        with patch("directory.gdms.GDMSClient._request") as remote:
            self.assertContains(self.client.get(self.url), "Deregister Bedroom?")
            self.client.post(self.url, {})
            self.enrollment.refresh_from_db()
            self.assertIsNone(self.enrollment.deregistration_requested_at)
            self.request_removal()
            first = self.enrollment.deregistration_requested_at
            response = self.client.post(self.url, {"confirm": "on"})
        remote.assert_not_called()
        self.assertRedirects(response, self.detail_url)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.deregistration_requested_at, first)
        self.assertEqual(self.enrollment.deregistration_requested_by, self.parent)
        self.assertEqual(self.family.activity.filter(description__startswith="Requested phone deregistration").count(), 1)
        self.assertTrue(Device.objects.filter(pk=self.device_id).exists())
        self.assertContains(self.client.get(self.detail_url), "Removing FrontPorch access")

    def test_other_family_revoked_guardian_login_csrf_and_feature_gate(self):
        other = Family.objects.create(name="Hill House")
        user = User.objects.create_user(username="hill")
        Parent.objects.create(user=user, family=other, display_name="Alex")
        self.client.force_login(user)
        for url in (self.url, self.confirm_url):
            self.assertEqual(self.client.post(url, {"confirm": "on"}).status_code, 404)
        self.client.force_login(self.user)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(self.url, {"confirm": "on"}).status_code, 403)
        self.assertEqual(strict.post(self.confirm_url, {"confirm": "on"}).status_code, 403)
        self.assertEqual(self.client.get(self.confirm_url).status_code, 405)
        with override_settings(PHONE_ENROLLMENT_ENABLED=False):
            self.assertEqual(self.client.post(self.url, {"confirm": "on"}).status_code, 404)
        self.parent.is_guardian = False
        self.parent.save()
        self.assertEqual(self.client.post(self.url, {"confirm": "on"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {"confirm": "on"}).status_code, 302)
        self.enrollment.refresh_from_db()
        self.assertIsNone(self.enrollment.deregistration_requested_at)

    def test_reset_confirmation_requires_accepted_request_and_explicit_acknowledgement(self):
        self.request_removal()
        self.client.post(self.confirm_url, {"confirm": "on"})
        self.enrollment.refresh_from_db()
        self.assertIsNone(self.enrollment.reset_confirmed_at)
        self.enrollment.state = State.RESET_PENDING
        self.enrollment.save()
        PhoneEnrollmentOperation.objects.create(enrollment=self.enrollment, kind="reset", status="accepted", reference="42")
        self.client.post(self.confirm_url, {})
        self.enrollment.refresh_from_db()
        self.assertIsNone(self.enrollment.reset_confirmed_at)
        self.client.post(self.confirm_url, {"confirm": "on"})
        self.enrollment.refresh_from_db()
        self.assertIsNotNone(self.enrollment.reset_confirmed_at)
        self.assertEqual(self.enrollment.state, State.REMOVING)
        self.assertEqual(self.family.activity.filter(description__startswith="Confirmed the phone").count(), 1)

    def test_progress_and_confirmation_do_not_expose_secrets(self):
        self.request_removal()
        url = reverse("directory:phone_setup_progress", args=[self.enrollment.pk])
        for response in (self.client.get(self.detail_url), self.client.get(url)):
            for secret in (self.secret, self.enrollment.mac, self.enrollment.serial, self.enrollment.encrypted_bootstrap):
                self.assertNotIn(secret, response.content.decode())
            self.assertIn("no-store", response["Cache-Control"])
        data = self.client.get(url).json()
        self.assertFalse(data["finished"])
        self.assertEqual(data["extension"], "")

    def test_same_identity_stays_reserved_until_removal_and_can_then_move_families(self):
        data = {"person": "family", "friendly_name": "Kitchen",
                "mac": self.enrollment.mac, "serial": self.enrollment.serial, "possession": "on"}
        self.request_removal()
        register = reverse("directory:phone_setup_register")
        self.assertRedirects(self.client.post(register, data), self.detail_url)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PhoneEnrollment.objects.create(family=self.family, requested_by=self.parent, mac=data["mac"], serial="TEST00000002")
        self.enrollment.state = State.DEREGISTERED
        self.enrollment.save()
        other = Family.objects.create(name="Hill House")
        user = User.objects.create_user(username="hill")
        Parent.objects.create(user=user, family=other, display_name="Alex")
        self.client.force_login(user)
        self.assertEqual(self.client.post(register, data).status_code, 302)
        new = PhoneEnrollment.objects.exclude(pk=self.enrollment.pk).get()
        self.assertEqual(new.family, other)
        self.assertEqual(new.state, State.QUEUED)
        self.assertFalse(new.operations.exists())
        self.assertNotEqual(new.provider_name, self.enrollment.provider_name)

    def test_deregistered_record_is_removed_from_phone_list(self):
        self.enrollment.state = State.DEREGISTERED
        self.enrollment.save()
        self.assertNotContains(self.client.get(reverse("directory:phone_setup")), self.enrollment.friendly_name)


class DeregistrationWorkerTests(DeregistrationFixture):
    def setUp(self):
        super().setUp()
        self.now = timezone.now()
        self.provider, self.apply = Mock(), Mock()
        self.worker = EnrollmentWorker(self.provider, clock=lambda: self.now, apply=self.apply)
        self.row = {"mac": self.enrollment.mac, "sn": self.enrollment.serial,
                    "deviceName": self.enrollment.provider_name, "orgId": 1, "siteId": 2}
        self.provider.device.return_value = self.row
        self.provider.factory_reset.return_value = 42
        self.provider.task_by_name.return_value = None

    def tick(self):
        self.now += timedelta(seconds=15)
        self.worker.step(self.enrollment)
        self.enrollment.refresh_from_db()

    def reset_requested(self):
        self.request_removal()
        self.tick()
        self.tick()
        self.assertEqual(self.enrollment.state, State.RESET_PENDING)

    def confirm(self):
        self.client.post(self.confirm_url, {"confirm": "on"})
        self.enrollment.refresh_from_db()

    def test_full_removal_revokes_credentials_cancels_task_and_releases_phone(self):
        profile_path(self.enrollment).write_text("private profile")
        other = Device.objects.create(assigned_family=self.family, friendly_name="Kitchen",
            sip_extension="5200", sip_username="other-phone", sip_secret="other-secret")
        DialShortcut.objects.create(source_device=self.enrollment.device, digits="2",
            internal_target_device=other, approved_by=self.parent)
        DialShortcut.objects.create(source_device=other, digits="3",
            internal_target_device=self.enrollment.device, approved_by=self.parent)
        self.reset_requested()
        self.assertFalse(profile_path(self.enrollment).exists())
        self.assertFalse(Device.objects.filter(pk=self.device_id).exists())
        self.assertFalse(WireGuardPeer.objects.filter(pk=self.peer_id).exists())
        self.assertEqual(DialShortcut.objects.count(), 2)
        self.assertEqual(build_asterisk_configuration().shortcut_rules, ())
        self.assertEqual(self.enrollment.encrypted_bootstrap, "")
        self.assertNotIn(self.username, str(build_asterisk_configuration()))
        self.apply.assert_called_once_with(reload=True)
        self.provider.factory_reset.assert_called_once_with(
            mac=self.enrollment.mac, org_id=1, task_name="fp-reset-" + self.enrollment.pk.hex,
        )
        self.tick()
        self.provider.delete_device.assert_not_called()
        self.confirm()
        self.provider.task_by_name.return_value = {"id": 42, "taskType": 2}
        self.tick()
        self.provider.delete_task.assert_called_once_with(42)
        self.provider.delete_device.assert_not_called()
        self.provider.task_by_name.return_value = None
        self.tick()
        self.provider.delete_device.assert_called_once_with(mac=self.enrollment.mac, org_id=1)
        self.assertEqual(self.enrollment.state, State.REMOVING)
        self.provider.device.return_value = None
        self.tick()
        self.assertEqual(self.enrollment.state, State.DEREGISTERED)
        calls = self.provider.mock_calls[:]
        self.tick()
        self.assertEqual(self.provider.mock_calls, calls)
        self.assertEqual(self.family.activity.filter(description__startswith="Deregistered phone").count(), 1)
        allocate_phone(PhoneEnrollment.objects.create(family=self.family, requested_by=self.parent,
            assigned_child=self.child, friendly_name="Fresh phone",
            mac=self.enrollment.mac, serial=self.enrollment.serial))
        new = Device.objects.exclude(pk=other.pk).get()
        self.assertNotEqual(new.sip_username, self.username)
        self.assertNotEqual(new.sip_secret, self.secret)
        self.assertNotEqual(new.wireguard_peer_id, self.peer_id)

    def test_worker_refreshes_stale_work_item_and_never_reprovisions_it(self):
        stale = PhoneEnrollment.objects.get(pk=self.enrollment.pk)
        self.request_removal()
        self.worker.step(stale)
        self.assertFalse(Device.objects.filter(pk=self.device_id).exists())
        self.provider.configure_xml.assert_not_called()

    def test_lost_reset_response_reconciles_by_unique_task_and_never_repeats(self):
        self.request_removal()
        self.tick()
        self.provider.factory_reset.side_effect = GDMSTransportError("unknown")
        with self.assertRaises(GDMSTransportError):
            self.tick()
        self.provider.task_by_name.return_value = {"id": 42, "taskType": 2}
        self.tick()
        self.assertEqual(self.enrollment.state, State.RESET_PENDING)
        self.assertEqual(self.enrollment.operations.get(kind="reset").reference, "42")
        self.tick()
        self.provider.factory_reset.assert_called_once()

    def test_unknown_reset_without_task_evidence_keeps_claim_and_needs_help(self):
        self.request_removal()
        self.tick()
        PhoneEnrollmentOperation.objects.create(enrollment=self.enrollment, kind="reset")
        self.tick()
        self.assertEqual(self.enrollment.state, State.DEREGISTER_HELP)
        self.provider.factory_reset.assert_not_called()
        self.provider.delete_device.assert_not_called()

    def test_rejected_reset_does_not_release_claim_or_repeat(self):
        self.request_removal()
        self.tick()
        self.provider.factory_reset.side_effect = GDMSAPIError(30050)
        with self.assertRaises(GDMSAPIError):
            self.tick()
        self.tick()
        self.assertEqual(self.enrollment.state, State.DEREGISTER_HELP)
        self.provider.factory_reset.assert_called_once()
        self.provider.delete_device.assert_not_called()

    def test_uncertain_deletion_reconciles_absence_without_repeating(self):
        self.reset_requested()
        self.confirm()
        self.provider.delete_device.side_effect = GDMSTransportError("unknown")
        with self.assertRaises(GDMSTransportError):
            self.tick()
        self.provider.device.return_value = None
        self.tick()
        self.assertEqual(self.enrollment.state, State.DEREGISTERED)
        self.provider.delete_device.assert_called_once()

    def test_failed_deletion_retains_identity_and_check_again_only_reconciles(self):
        self.reset_requested()
        self.confirm()
        self.provider.delete_device.side_effect = GDMSAPIError(30050)
        with self.assertRaises(GDMSAPIError):
            self.tick()
        self.tick()
        self.assertEqual(self.enrollment.state, State.DEREGISTER_HELP)
        self.client.post(reverse("directory:phone_setup_check", args=[self.enrollment.pk]))
        self.tick()
        self.provider.delete_device.assert_called_once()
        self.assertEqual(self.enrollment.state, State.DEREGISTER_HELP)

    def test_foreign_provider_identity_is_never_reset_or_deleted(self):
        self.request_removal()
        self.tick()
        self.provider.device.return_value = {**self.row, "deviceName": "another-owner"}
        self.tick()
        self.assertEqual(self.enrollment.state, State.DEREGISTER_HELP)
        self.provider.factory_reset.assert_not_called()
        self.provider.delete_device.assert_not_called()

    def test_task_identity_mismatch_blocks_deletion(self):
        self.reset_requested()
        self.confirm()
        self.provider.task_by_name.return_value = {"id": 43, "taskType": 2}
        self.tick()
        self.assertEqual(self.enrollment.state, State.DEREGISTER_HELP)
        self.provider.delete_task.assert_not_called()
        self.provider.delete_device.assert_not_called()

    def test_pending_upgrade_is_cancelled_before_reset(self):
        PhoneEnrollmentOperation.objects.create(enrollment=self.enrollment, kind="upgrade", status="accepted", reference="41")
        self.request_removal()
        self.tick()
        self.provider.task_by_name.return_value = {"id": 41, "taskType": 3}
        self.tick()
        self.provider.delete_task.assert_called_once_with(41)
        self.provider.factory_reset.assert_not_called()
        self.provider.task_by_name.return_value = None
        self.tick()
        self.provider.factory_reset.assert_called_once()

    def test_failed_pbx_apply_is_retried_before_any_factory_reset(self):
        self.request_removal()
        self.apply.side_effect = RuntimeError("local apply failed")
        with self.assertRaises(RuntimeError):
            self.tick()
        self.enrollment.refresh_from_db()
        self.assertIsNone(self.enrollment.removal_applied_at)
        self.provider.factory_reset.assert_not_called()
        self.apply.side_effect = None
        self.tick()
        self.assertIsNotNone(self.enrollment.removal_applied_at)
        self.assertEqual(self.family.activity.filter(description__startswith="Removed calling access").count(), 1)

    def test_never_enrolled_phone_can_be_cancelled_without_remote_mutations(self):
        self.enrollment.gdms_added_at = None
        self.enrollment.save()
        self.request_removal()
        self.tick()
        self.tick()
        self.assertEqual(self.enrollment.state, State.DEREGISTERED)
        self.assertEqual(self.provider.mock_calls, [])

    def test_shared_manual_gateway_is_preserved(self):
        peer = self.enrollment.device.wireguard_peer
        peer.provisioning_method = WireGuardPeer.Provisioning.MANUAL
        peer.save()
        Device.objects.create(assigned_child=self.child, friendly_name="Other phone", sip_extension=self.enrollment.device.sip_extension,
            sip_username="other-phone", sip_secret="other-secret", wireguard_peer=peer)
        self.request_removal()
        self.tick()
        peer.refresh_from_db()
        self.assertTrue(peer.is_active)
        self.assertEqual(peer.devices.count(), 1)

    def test_worker_selects_removal_even_when_ready_phone_has_retired_bootstrap(self):
        PhoneEnrollmentOperation.objects.create(enrollment=self.enrollment, kind="bootstrap", status="accepted")
        PhoneEnrollmentOperation.objects.create(enrollment=self.enrollment, kind="retire", status="accepted")
        from directory.management.commands import provision_phones
        with patch.object(provision_phones, "validate_configuration"), patch.object(
            provision_phones, "EnrollmentWorker", return_value=self.worker,
        ), patch.object(provision_phones, "close_old_connections"):
            with patch.object(self.worker, "step") as step:
                call_command("provision_phones", once=True)
                step.assert_not_called()
            self.request_removal()
            call_command("provision_phones", once=True)
        self.assertFalse(Device.objects.filter(pk=self.device_id).exists())
