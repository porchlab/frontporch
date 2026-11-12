import hashlib
import io
import os
import runpy
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from directory.enrollment_worker import (
    validate_configuration, validate_firmware_configuration, verify_firmware_download,
)


class FirmwareEnvironmentTests(SimpleTestCase):
    def configured(self, **overrides):
        environment = dict.fromkeys((
            "WP816_FIRMWARE_VERSION", "WP816_FIRMWARE_URL", "WP816_FIRMWARE_SHA256",
        ), "")
        with patch.dict(os.environ, environment | overrides):
            return runpy.run_path(str(settings.BASE_DIR / "frontporch/settings.py"))

    def test_existing_deployments_keep_reviewed_version_and_checksum(self):
        configured = self.configured()
        self.assertEqual(configured["WP816_FIRMWARE_VERSION"], "1.0.3.39")
        self.assertEqual(configured["WP816_FIRMWARE_SHA256"],
            "591babdf593e084a7d398740cf9d35bf446fcaae96f30235781e7cca64d59be9")

    def test_all_firmware_fields_can_be_overridden(self):
        values = {"WP816_FIRMWARE_VERSION": "1.0.3.40",
            "WP816_FIRMWARE_URL": "https://firmware.grandstream.com/BETA/wp8x6fw.bin",
            "WP816_FIRMWARE_SHA256": "a" * 64}
        configured = self.configured(**values)
        self.assertEqual({key: configured[key] for key in values}, values)

    def test_different_version_does_not_inherit_old_checksum(self):
        configured = self.configured(WP816_FIRMWARE_VERSION="1.0.3.40")
        self.assertEqual(configured["WP816_FIRMWARE_SHA256"], "")
        with override_settings(**{key: configured[key] for key in (
                "WP816_FIRMWARE_VERSION", "WP816_FIRMWARE_SHA256")}):
            with self.assertRaisesMessage(ImproperlyConfigured, "WP816_FIRMWARE_SHA256"):
                validate_firmware_configuration()


@override_settings(WP816_FIRMWARE_VERSION="1.0.3.39", WP816_FIRMWARE_SHA256="a" * 64,
    WP816_FIRMWARE_URL="https://firmware.grandstream.com/wp8x6fw.bin")
class FirmwareValidationTests(SimpleTestCase):
    def test_valid_configuration(self):
        validate_firmware_configuration()

    def test_invalid_versions_and_checksums_fail_before_provider_access(self):
        cases = {
            "WP816_FIRMWARE_VERSION": ["", "latest", "1.0.3", "1.0.3.40-beta", "1.0.3.9999", "1.0.3.39\n"],
            "WP816_FIRMWARE_SHA256": ["", "a" * 63, "z" * 64, "a" * 64 + "\n"],
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value), override_settings(
                        PHONE_ENROLLMENT_ENABLED=True, **{key: value}):
                    with patch("directory.enrollment_worker.GDMSSettings.from_django") as provider:
                        with self.assertRaises(ImproperlyConfigured):
                            validate_configuration()
                    provider.assert_not_called()

    def test_firmware_url_still_requires_official_https_binary(self):
        for url in ("http://firmware.grandstream.com/wp8x6fw.bin",
                "https://example.com/wp8x6fw.bin", "https://firmware.grandstream.com:bad/wp8x6fw.bin",
                "https://user@firmware.grandstream.com/wp8x6fw.bin",
                "https://firmware.grandstream.com/wp8x6fw.bin?version=latest",
                "https://firmware.grandstream.com/other.bin"):
            with self.subTest(url=url), override_settings(WP816_FIRMWARE_URL=url):
                with self.assertRaises(ImproperlyConfigured):
                    validate_firmware_configuration()

    @patch("directory.enrollment_worker.build_opener")
    def test_download_uses_configured_digest_and_rejects_changed_bytes(self, opener):
        payload = b"test firmware bytes"
        with override_settings(WP816_FIRMWARE_SHA256=hashlib.sha256(payload).hexdigest()):
            opener.return_value.open.return_value = io.BytesIO(payload)
            verify_firmware_download(settings.WP816_FIRMWARE_URL)
            opener.return_value.open.return_value = io.BytesIO(payload + b"changed")
            with self.assertRaisesMessage(ValueError, "Firmware differs"):
                verify_firmware_download(settings.WP816_FIRMWARE_URL)
