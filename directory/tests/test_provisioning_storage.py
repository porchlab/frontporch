import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from frontporch.provisioning_storage import (
    check_worker_health, check_worker_storage, prepare_pbx_storage, ProvisioningStorageError,
)


class ProvisioningStorageTests(SimpleTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.paths = {name: self.root / name for name in ("profiles", "receipts", "config", "sounds")}
        for path in self.paths.values():
            path.mkdir()
        (self.paths["sounds"] / "tts").mkdir()
        self.env = dict(zip(
            ("PHONE_PROFILE_DIR", "PHONE_RECEIPT_DIR", "ASTERISK_GENERATED_CONFIG_DIR", "ASTERISK_CUSTOM_SOUNDS_DIR"),
            map(str, self.paths.values()),
        ))

    def test_probe_preserves_existing_files_and_cleans_up(self):
        fixtures = [self.paths["config"] / "pjsip_frontporch.conf", self.paths["profiles"] / "lease.json",
                    self.paths["sounds"] / "tts" / "cached.ulaw", self.paths["receipts"] / "receipt.json"]
        for path in fixtures:
            path.write_bytes(b"keep existing data")
        check_worker_storage(*self.paths.values())
        self.assertEqual({p for p in self.root.rglob("*") if p.is_file()}, set(fixtures))
        for path in fixtures:
            self.assertEqual(path.read_bytes(), b"keep existing data")

    def test_missing_or_symlinked_storage_is_rejected(self):
        for name in ("profiles", "receipts", "config"):
            with self.subTest(name=name):
                path = self.paths[name]
                path.rmdir()
                with self.assertRaises(ProvisioningStorageError):
                    check_worker_storage(*self.paths.values())
                path.symlink_to(self.paths["sounds"], target_is_directory=True)
                with self.assertRaises(ProvisioningStorageError):
                    check_worker_storage(*self.paths.values())
                path.unlink()
                path.mkdir()

    def test_prepare_refuses_a_symlink_instead_of_changing_its_target(self):
        path = self.paths["config"]
        path.rmdir()
        path.symlink_to(self.paths["receipts"], target_is_directory=True)
        with patch("frontporch.provisioning_storage.os.fchown") as chown:
            with self.assertRaises(ProvisioningStorageError):
                prepare_pbx_storage(path, self.paths["sounds"])
        chown.assert_not_called()

    def test_fresh_heartbeat_cannot_hide_a_storage_failure(self):
        (self.paths["profiles"] / "worker-health.json").write_text(json.dumps({"at": 1000}))
        check_worker_health(self.env, clock=lambda: 1001)
        self.paths["config"].rmdir()
        with self.assertRaisesRegex(ProvisioningStorageError, "PBX configuration"):
            check_worker_health(self.env, clock=lambda: 1001)

    def test_health_rejects_missing_malformed_future_and_stale_heartbeat(self):
        heartbeat = self.paths["profiles"] / "worker-health.json"
        with self.assertRaises(ProvisioningStorageError):
            check_worker_health(self.env, clock=lambda: 1000)
        for content in ('invalid', '{}', '{"at": true}', '{"at": "1000"}', '{"at": 1001}', '{"at": 400}'):
            with self.subTest(content=content):
                heartbeat.write_text(content)
                with self.assertRaises(ProvisioningStorageError):
                    check_worker_health(self.env, clock=lambda: 1000)

    @override_settings(PHONE_ENROLLMENT_ENABLED=False)
    def test_web_startup_does_not_prepare_storage_without_enrollment(self):
        with patch("directory.management.commands.prepare_phone_provisioning_storage.prepare_pbx_storage") as prepare:
            call_command("prepare_phone_provisioning_storage", stdout=io.StringIO())
        prepare.assert_not_called()

    def test_worker_startup_rejects_bad_storage_before_processing_jobs(self):
        from directory.enrollment_worker import validate_configuration
        from django.core.exceptions import ImproperlyConfigured
        with override_settings(PHONE_ENROLLMENT_ENABLED=True, GDMS_ORG_ID="1", GDMS_SITE_ID="2",
                WP816_FIRMWARE_URL="https://firmware.grandstream.com/wp8x6fw.bin",
                PHONE_PROFILE_PUBLIC_URL="https://phones.example.com/phone-profiles", **self.env), \
                patch("directory.enrollment_worker.GDMSSettings.from_django"), \
                patch("directory.enrollment_worker.wireguard.cipher"):
            self.paths["config"].rmdir()
            with self.assertRaisesRegex(ImproperlyConfigured, "PBX configuration"):
                validate_configuration()
