import base64
import json
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import ProtectedError
from django.test import RequestFactory, TestCase, override_settings

from directory.admin import WireGuardPeerAdmin, WireGuardPeerForm
from directory.asterisk.builder import build_asterisk_configuration
from directory.asterisk.renderer import AsteriskConfigRenderer
from directory.models import Device, Family, FamilyActivity, WireGuardPeer
from directory.tests.factories import create_user
from directory.tests.test_wireguard import SERVER
from directory.wireguard import (
    create_peer, desired_snapshot, generate_peer_keys, import_peers,
    imported_client_keys, parse_legacy_config, peer_secrets, reconcile_once,
)
from frontporch.vpn_config import ServerConfig, VPNConfigurationError


def public_key(number):
    return base64.b64encode(bytes([number]) * 32).decode()


def derived_key(private):
    return base64.b64encode(X25519PrivateKey.from_private_bytes(
        base64.b64decode(private)).public_key().public_bytes_raw()).decode()


@override_settings(WIREGUARD_SERVER_ADDRESS="10.77.0.1/24",
                   WIREGUARD_ENCRYPTION_KEY=Fernet.generate_key().decode())
class FamilyPeerTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="River family")
        self.other = Family.objects.create(name="Hill family")

    def peer(self, number=2, **values):
        peer = WireGuardPeer(family=self.family, name=f"Connection {number}",
                             public_key=public_key(number), **values)
        if peer.provisioning_method == "gdms":
            generate_peer_keys(peer)
        peer.save()
        return peer

    def phone(self, peer, number=1, family=None):
        return Device.objects.create(assigned_family=family or self.family, friendly_name=f"Test phone {number}",
                                     sip_extension=str(2000 + number), sip_username=f"fictional-phone-{number}",
                                     sip_secret="fixture-only-password", wireguard_peer=peer)

    def test_family_can_have_mixed_peers_and_manual_gateway_can_serve_multiple_phones(self):
        manual = self.peer()
        managed = self.peer(3, provisioning_method="gdms")
        self.phone(manual, 1)
        self.phone(manual, 2)
        self.phone(managed, 3)
        self.assertEqual(self.family.wireguard_peers.count(), 2)
        self.assertEqual(manual.devices.count(), 2)
        self.assertNotEqual(manual.client_address, managed.client_address)
        with self.assertRaises(ValidationError):
            self.phone(managed, 4)
        manual.provisioning_method = "gdms"
        with self.assertRaises(ValidationError):
            manual.save()

    def test_foreign_family_assignment_transfer_and_identity_edits_are_denied(self):
        peer = self.peer()
        with self.assertRaises(ValidationError):
            self.phone(peer, family=self.other)
        phone = self.phone(peer)
        peer.family = self.other
        with self.assertRaises(ValidationError):
            peer.save()
        peer.refresh_from_db()
        peer.public_key = public_key(4)
        with self.assertRaises(ValidationError):
            peer.save()
        peer.refresh_from_db()
        peer.client_address = "10.77.0.10"
        with self.assertRaises(ValidationError):
            peer.save()
        phone.refresh_from_db()
        self.assertEqual(phone.owning_family, self.family)

    def test_revoked_addresses_are_not_reallocated(self):
        peer = self.peer()
        peer.is_active = False
        peer.save()
        second = self.peer(3)
        self.assertNotEqual(second.client_address, peer.client_address)

    def test_generated_secrets_are_encrypted_and_bound_to_the_peer(self):
        first = create_peer(family=self.family, name="Kitchen phone", provisioning_method="gdms")
        second = create_peer(family=self.family, name="Hall phone", provisioning_method="manual")
        secrets = peer_secrets(first)
        self.assertTrue(secrets["private_key"])
        self.assertTrue(secrets["preshared_key"])
        self.assertNotIn(secrets["private_key"], first.encrypted_secrets)
        self.assertNotIn(secrets["preshared_key"], first.encrypted_secrets)
        second.encrypted_secrets = first.encrypted_secrets
        with self.assertRaises(VPNConfigurationError):
            peer_secrets(second)
        self.assertEqual(FamilyActivity.objects.filter(family=self.family).count(), 2)
        for event in FamilyActivity.objects.all():
            self.assertNotIn(secrets["private_key"], json.dumps(event.details))

    def test_snapshot_and_pbx_both_remove_a_revoked_peer(self):
        peer = self.peer()
        device = self.phone(peer)
        snapshot = desired_snapshot(ServerConfig.parse(SERVER), now=1000)
        self.assertEqual(snapshot["peers"][0]["address"], peer.client_address)
        config = build_asterisk_configuration()
        text = AsteriskConfigRenderer().render_pjsip(config)
        self.assertIn("media_address=10.77.0.1", text)
        self.assertIn("bind_rtp_to_media_address=no", text)
        self.assertIn("qualify_frequency=25", text)
        peer.is_active = False
        peer.save()
        self.assertEqual(desired_snapshot(ServerConfig.parse(SERVER), now=1000)["peers"], [])
        self.assertNotIn(device.sip_username, AsteriskConfigRenderer().render_pjsip(build_asterisk_configuration()))

    def test_builder_denies_foreign_peer_even_if_model_validation_was_bypassed(self):
        peer = self.peer()
        device = self.phone(peer)
        WireGuardPeer.objects.filter(pk=peer.pk).update(family=self.other)
        text = AsteriskConfigRenderer().render_pjsip(build_asterisk_configuration())
        self.assertNotIn(device.sip_username, text)

    def test_admin_disabling_is_audited_and_does_not_display_encrypted_secrets(self):
        peer = self.peer()
        staff = create_user(is_staff=True, is_superuser=True)
        request = RequestFactory().post("/admin/")
        request.user = staff
        admin = WireGuardPeerAdmin(WireGuardPeer, AdminSite())
        admin.disable_peers(request, WireGuardPeer.objects.filter(pk=peer.pk))
        peer.refresh_from_db()
        self.assertFalse(peer.is_active)
        self.assertEqual(FamilyActivity.objects.get().actor, staff)
        self.assertIn("encrypted_secrets", admin.exclude)
        self.assertIn("public_key", admin.get_readonly_fields(request, peer))

    def test_admin_form_allocates_address_and_keeps_client_keys_optional_for_imported_peers(self):
        form = WireGuardPeerForm(data={"family": self.family.pk, "name": "Existing gateway",
                                       "provisioning_method": "manual", "public_key": public_key(9),
                                       "client_address": "", "persistent_keepalive": 25, "is_active": True})
        self.assertTrue(form.is_valid(), form.errors)
        peer = form.save()
        self.assertEqual(peer.client_address, "10.77.0.2")
        self.assertEqual(peer_secrets(peer)["private_key"], "")

    def test_admin_generates_a_downloadable_managed_connection_but_rejects_unknown_client_keys(self):
        data = {"family": self.family.pk, "name": "New phone", "provisioning_method": "gdms",
                "public_key": "", "client_address": "", "persistent_keepalive": 25, "is_active": True}
        form = WireGuardPeerForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        peer = form.save()
        self.assertEqual(derived_key(peer_secrets(peer)["private_key"]), peer.public_key)
        form = WireGuardPeerForm(data={**data, "name": "Unknown key", "public_key": public_key(9)})
        self.assertFalse(form.is_valid())
        self.assertIn("provisioning_method", form.errors)

    @override_settings(WIREGUARD_ENDPOINT="vpn.example.com:51820", WIREGUARD_SERVER_PUBLIC_KEY=public_key(8))
    def test_configuration_download_requires_change_permission_is_uncacheable_and_audited(self):
        peer = create_peer(family=self.family, name="New phone", provisioning_method="gdms")
        request = RequestFactory().post("/admin/")
        request.user = create_user(is_staff=True)
        admin = WireGuardPeerAdmin(WireGuardPeer, AdminSite())
        with self.assertRaises(PermissionDenied):
            admin.download_configuration(request, WireGuardPeer.objects.filter(pk=peer.pk))
        self.assertEqual(FamilyActivity.objects.count(), 1)
        request.user = create_user(is_staff=True, is_superuser=True)
        response = admin.download_configuration(request, WireGuardPeer.objects.filter(pk=peer.pk))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(peer_secrets(peer)["private_key"], response.content.decode())
        self.assertEqual(FamilyActivity.objects.count(), 2)
        self.assertNotIn(peer_secrets(peer)["private_key"], json.dumps(list(
            FamilyActivity.objects.values("description", "details"))))

    def test_unrecoverable_and_disabled_peers_have_no_download(self):
        legacy = self.peer()
        disabled = create_peer(family=self.family, name="Disabled phone", provisioning_method="gdms")
        disabled.is_active = False
        disabled.save()
        request = RequestFactory().post("/admin/")
        request.user = create_user(is_staff=True, is_superuser=True)
        admin = WireGuardPeerAdmin(WireGuardPeer, AdminSite())
        before = FamilyActivity.objects.count()
        with patch.object(admin, "message_user"):
            for peer in (legacy, disabled):
                self.assertIsNone(admin.download_configuration(request, WireGuardPeer.objects.filter(pk=peer.pk)))
        self.assertEqual(FamilyActivity.objects.count(), before)

    def test_failed_bulk_deletion_does_not_record_successful_removal(self):
        self.phone(self.peer())
        self.peer(3)
        request = RequestFactory().post("/admin/")
        request.user = create_user(is_staff=True, is_superuser=True)
        admin = WireGuardPeerAdmin(WireGuardPeer, AdminSite())
        with self.assertRaises(ProtectedError):
            admin.delete_queryset(request, WireGuardPeer.objects.all())
        self.assertEqual(WireGuardPeer.objects.count(), 2)
        self.assertFalse(FamilyActivity.objects.exists())


@override_settings(WIREGUARD_SERVER_ADDRESS="10.77.0.1/24",
                   WIREGUARD_ENCRYPTION_KEY=Fernet.generate_key().decode())
class LegacyImportTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="River family")
        self.other = Family.objects.create(name="Hill family")
        self.text = f"""[Interface]
PrivateKey = {public_key(8)}
ListenPort = 51820
[Peer]
PublicKey = {public_key(2)}
AllowedIPs = 10.77.0.2/32
Endpoint = 192.0.2.10:40000
PersistentKeepalive = 25
[Peer]
PublicKey = {public_key(3)}
AllowedIPs = 10.77.0.3/32
"""
        self.legacy = parse_legacy_config(self.text)
        self.assignments = [
            {"client_address": "10.77.0.2", "family_id": self.family.pk, "name": "Existing gateway",
             "provisioning_method": "manual"},
            {"client_address": "10.77.0.3", "family_id": self.other.pk, "name": "Existing phone",
             "provisioning_method": "manual"},
        ]

    def test_preview_does_not_write_and_import_preserves_keys_addresses_and_optional_psk(self):
        self.assertEqual(len(import_peers(self.legacy, self.assignments)), 2)
        self.assertEqual(WireGuardPeer.objects.count(), 0)
        self.assertEqual(FamilyActivity.objects.count(), 0)
        imported = import_peers(self.legacy, self.assignments, apply=True)
        self.assertEqual([p.public_key for p in imported], [public_key(2), public_key(3)])
        self.assertEqual([p.client_address for p in imported], ["10.77.0.2", "10.77.0.3"])
        self.assertEqual(imported[0].persistent_keepalive, 25)
        self.assertEqual(peer_secrets(imported[0]), {"private_key": "", "preshared_key": ""})
        self.assertEqual(FamilyActivity.objects.count(), 2)
        with self.assertRaises(ValidationError):
            import_peers(self.legacy, self.assignments, apply=True)
        self.assertEqual(WireGuardPeer.objects.count(), 2)

    def test_missing_or_conflicting_mapping_does_not_partially_import(self):
        for assignments in (self.assignments[:1],
                            [self.assignments[0], {**self.assignments[1], "family_id": 999999}],
                            [self.assignments[0], {**self.assignments[1], "client_address": "10.77.0.2"}]):
            with self.assertRaises(ValidationError):
                import_peers(self.legacy, assignments, apply=True)
            self.assertEqual(WireGuardPeer.objects.count(), 0)

    def test_foreign_phone_cannot_be_assigned_by_import(self):
        phone = Device.objects.create(assigned_family=self.other, friendly_name="Other family phone",
                                      sip_extension="2001", sip_username="fixture-phone", sip_secret="test-only")
        assignments = deepcopy(self.assignments)
        assignments[0]["device_ids"] = [phone.pk]
        with self.assertRaises(ValidationError):
            import_peers(self.legacy, assignments, apply=True)
        self.assertEqual(WireGuardPeer.objects.count(), 0)

    def test_routes_and_unknown_hooks_need_explicit_review(self):
        for text in (self.text.replace("10.77.0.2/32", "10.77.0.0/24"),
                     self.text + "PostUp = dangerous\n", self.text.replace("ListenPort = 51820", "ListenPort = bad")):
            with self.assertRaises(VPNConfigurationError):
                parse_legacy_config(text)

    def test_managed_import_preserves_a_verified_client_key_and_optional_psk(self):
        private, psk = public_key(10), public_key(11)
        legacy = parse_legacy_config(self.text.replace(public_key(3), derived_key(private)) + f"PresharedKey = {psk}\n")
        client = (f"[Interface]\nPrivateKey = {private}\nAddress = 10.77.0.3/32\n"
                  f"[Peer]\nPublicKey = {derived_key(public_key(8))}\nPresharedKey = {psk}\n")
        assignments = deepcopy(self.assignments)
        assignments[1]["provisioning_method"] = "gdms"
        with self.assertRaises(ValidationError):
            import_peers(legacy, assignments, apply=True)
        self.assertFalse(WireGuardPeer.objects.exists())
        for invalid in (client.replace(private, public_key(12)),
                        client.replace("10.77.0.3", "10.77.0.2"),
                        client.replace(derived_key(public_key(8)), public_key(8)),
                        client.replace(psk, public_key(12)), client + "PostUp = unwanted\n"):
            with self.assertRaises(VPNConfigurationError):
                imported_client_keys(legacy, [invalid])
        imported = import_peers(legacy, assignments, apply=True,
                                client_keys=imported_client_keys(legacy, [client]))
        self.assertEqual(peer_secrets(imported[1]), {"private_key": private, "preshared_key": psk})
        self.assertNotIn(private, imported[1].encrypted_secrets)


@override_settings(WIREGUARD_SERVER_ADDRESS="10.77.0.1/24", WIREGUARD_ENABLED=True)
class ReconcilerTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name in ("desired", "observed"):
            (self.root / name).mkdir()
        self.network = self.root / "network.json"
        self.network.write_text(json.dumps({k: v for k, v in SERVER.items() if k != "private_key"}))
        self.settings_override = override_settings(
            WIREGUARD_DESIRED_DIR=str(self.root / "desired"),
            WIREGUARD_OBSERVED_DIR=str(self.root / "observed"), WIREGUARD_NETWORK_FILE=str(self.network))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        family = Family.objects.create(name="River family")
        self.peer = WireGuardPeer.objects.create(family=family, name="Gateway", public_key=public_key(2))

    def publish(self, now):
        with patch("directory.wireguard.time.time", return_value=now):
            reconcile_once()
        return json.loads((self.root / "desired/peers.json").read_text())

    def report(self, snapshot, **values):
        (self.root / "observed/status.json").write_text(json.dumps({
            "revision": snapshot["revision"], "state": "active", "observed_at": 1001,
            "peers": [{"id": str(self.peer.pk), "latest_handshake": 1000}], **values,
        }))

    def test_only_fresh_current_acknowledgements_update_status_and_revocation_is_published(self):
        first = self.publish(1000)
        self.report(first)
        second = self.publish(1002)
        self.peer.refresh_from_db()
        self.assertEqual(self.peer.last_applied_at.timestamp(), 1001)
        self.assertEqual(self.peer.last_handshake_at.timestamp(), 1000)
        self.report(second, observed_at=1003, peers=[{"id": str(self.peer.pk), "latest_handshake": 1003}])
        self.peer.is_active = False
        self.peer.save()
        self.assertEqual(self.publish(1004)["peers"], [])
        self.peer.refresh_from_db()
        self.assertEqual(self.peer.last_applied_at.timestamp(), 1001)
        self.assertEqual((self.root / "desired/peers.json").stat().st_mode & 0o777, 0o600)

    def test_stale_malformed_or_unrelated_reports_do_not_acknowledge_a_peer(self):
        for changes in ({"observed_at": 900}, {"observed_at": 1003}, {"state": "expired"},
                        {"revision": "wrong"}, {"peers": [None]}, {"peers": "invalid"},
                        {"peers": [{"id": str(self.peer.pk), "latest_handshake": 1003}]}):
            first = self.publish(1000)
            self.report(first, **changes)
            self.publish(1002)
            self.peer.refresh_from_db()
            self.assertIsNone(self.peer.last_applied_at)
