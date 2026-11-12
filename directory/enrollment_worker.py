"""One durable step per enrollment. Never reissue an uncertain provider write.

DB state is committed before external effects. One PostgreSQL session advisory
lock serializes workers across restarts/deployments; HTTP requests cannot run it.
"""

import base64
import hashlib
import json
import re
import secrets
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from .gdms import _NoRedirects

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from frontporch.phone_profiles import MAX_LEASE_SECONDS, password_digest
from frontporch.provisioning_storage import check_worker_storage, ProvisioningStorageError
from frontporch.vpn_runtime import atomic_private_file
from . import wireguard, wp816
from .asterisk.ami import AsteriskManagerClient, AsteriskManagerSettings
from .asterisk.apply import apply_asterisk_configuration
from .gdms import GDMSClient, GDMSSettings, GDMSError, GDMSAPIError, positive_id
from .models import (Device, ExternalNumberExtension, FamilyActivity, Parent, PhoneEnrollment,
                     PhoneEnrollmentOperation, PhoneEnrollmentState as State, WireGuardPeer, lock_extension_namespace)

TARGET_FIRMWARE = "1.0.3.39"
FIRMWARE_SHA256 = "591babdf593e084a7d398740cf9d35bf446fcaae96f30235781e7cca64d59be9"
TERMINAL = (State.READY, State.HELP, State.CANCELLED, State.DEREGISTER_HELP, State.DEREGISTERED)


def verify_firmware_download(url):
    """Do not queue a mutable vendor download URL after its content changes."""
    digest, size = hashlib.sha256(), 0
    deadline = time.monotonic() + 90
    with build_opener(_NoRedirects()).open(Request(url), timeout=30) as response:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 80 * 1024 * 1024 or time.monotonic() > deadline:
                raise ValueError("Firmware exceeds the reviewed size bound.")
            digest.update(chunk)
    if digest.hexdigest() != FIRMWARE_SHA256:
        raise ValueError("Firmware differs from the reviewed release.")



def validate_configuration():
    if not settings.PHONE_ENROLLMENT_ENABLED:
        raise ImproperlyConfigured("Phone enrollment is disabled.")
    positive_id(settings.GDMS_ORG_ID)
    positive_id(settings.GDMS_SITE_ID)
    GDMSSettings.from_django()
    wireguard.cipher()
    # Both URLs are operator-owned, never supplied by a parent or provider reply.
    firmware = urlsplit(settings.WP816_FIRMWARE_URL)
    if (firmware.scheme != "https" or firmware.hostname != "firmware.grandstream.com"
            or firmware.port not in (None, 443) or firmware.username or firmware.password
            or firmware.query or firmware.fragment or not firmware.path.endswith("/wp8x6fw.bin")):
        raise ImproperlyConfigured("Configure the reviewed official WP816 firmware URL.")
    wp816.bootstrap_profile("000000000001", settings.PHONE_PROFILE_PUBLIC_URL, "check", "check")
    for name in ("PHONE_PROFILE_DIR", "PHONE_RECEIPT_DIR"):
        path = getattr(settings, name)
        if not path or not Path(path).is_dir():
            raise ImproperlyConfigured("Configure private profile and receipt directories.")
    try:
        check_worker_storage(settings.PHONE_PROFILE_DIR, settings.PHONE_RECEIPT_DIR,
            settings.ASTERISK_GENERATED_CONFIG_DIR, settings.ASTERISK_CUSTOM_SOUNDS_DIR)
    except ProvisioningStorageError as error:
        raise ImproperlyConfigured(str(error)) from None


def save(enrollment, **values):
    for key, value in values.items():
        setattr(enrollment, key, value)
    enrollment.save(update_fields=[*values, "updated_at"])


def help_needed(enrollment, problem):
    revoke_profile(enrollment)
    save(enrollment, state=State.HELP, problem=problem)
    FamilyActivity.objects.create(family=enrollment.family, actor=None,
        description=f"Phone setup needs attention: {enrollment.friendly_name}.",
        details={"enrollment_id": str(enrollment.pk), "reason": problem})


def profile_path(enrollment):
    return Path(settings.PHONE_PROFILE_DIR) / (enrollment.pk.hex + ".json")


def revoke_profile(enrollment):
    profile_path(enrollment).unlink(missing_ok=True)


def operation(enrollment, kind, callback):
    """Return None when already attempted, including a crash/lost response."""
    entry, created = PhoneEnrollmentOperation.objects.get_or_create(enrollment=enrollment, kind=kind)
    if not created:
        return None
    try:
        result = callback()
    except GDMSAPIError:
        entry.status = "rejected"
        entry.save(update_fields=["status", "updated_at"])
        raise
    # Transport/protocol failures leave 'started', requiring reconciliation.
    entry.status = "accepted"
    if kind in ("upgrade", "reset"):
        entry.reference = str(result)
    entry.save(update_fields=["status", "reference", "updated_at"])
    return entry


def owned_inventory(enrollment, row):
    return (row and row.get("deviceName") == enrollment.provider_name
            and str(row.get("sn", "")).upper() == enrollment.serial
            and row.get("orgId") == enrollment.org_id and row.get("siteId") == enrollment.site_id)


def contacts_available(username):
    # Fixed read-only CLI; no request or database value is interpolated into it.
    client = AsteriskManagerClient(AsteriskManagerSettings(
        host=settings.ASTERISK_AMI_HOST, port=settings.ASTERISK_AMI_PORT,
        username=settings.ASTERISK_AMI_USERNAME, password=settings.ASTERISK_AMI_PASSWORD,
        timeout=settings.ASTERISK_AMI_TIMEOUT,
    ))
    result = client.run_cli_commands(("pjsip show contacts",))[0].output
    return bool(re.search(r"(?m)^\s*Contact:\s+" + re.escape(username) + r"/sip:\S+\s+\S+\s+Avail\s", result))


@transaction.atomic
@sensitive_variables()
def allocate_phone(enrollment):
    lock_extension_namespace()
    enrollment.refresh_from_db()
    if enrollment.device_id:
        return
    peer = wireguard.create_peer(family=enrollment.family, name="WP816 " + enrollment.pk.hex[:12],
        provisioning_method=WireGuardPeer.Provisioning.GDMS, actor=enrollment.requested_by.user)
    if enrollment.assigned_parent_id:
        extension = enrollment.assigned_parent.dial_extension
    elif enrollment.assigned_child_id:
        extension = Device.objects.filter(assigned_child=enrollment.assigned_child).values_list("sip_extension", flat=True).first()
    else:
        extension = Device.objects.filter(assigned_family=enrollment.family).values_list("sip_extension", flat=True).first()
    device = Device.objects.create(
        assigned_child=enrollment.assigned_child, assigned_parent=enrollment.assigned_parent,
        assigned_family=enrollment.family if not (enrollment.assigned_child_id or enrollment.assigned_parent_id) else None,
        friendly_name=enrollment.friendly_name, sip_extension=extension or ExternalNumberExtension._assign_extension(),
        sip_username="phone-" + secrets.token_hex(12), sip_secret=secrets.token_urlsafe(32),
        wireguard_peer=peer, is_active=True,
    )
    # The public portal cannot decrypt this. Bind it to this enrollment identity.
    bootstrap = {"id": enrollment.pk.hex, "username": secrets.token_hex(12), "password": secrets.token_urlsafe(32)}
    save(enrollment, device=device, encrypted_bootstrap=wireguard.cipher().encrypt(json.dumps(bootstrap).encode()).decode())


@sensitive_variables()
def credentials(enrollment):
    data = json.loads(wireguard.cipher().decrypt(enrollment.encrypted_bootstrap.encode()))
    if data.get("id") != enrollment.pk.hex:
        raise ValueError("Bootstrap identity mismatch.")
    return data


@sensitive_variables()
def publish_profile(enrollment, now):
    auth = credentials(enrollment)
    device = enrollment.device
    xml = wp816.device_profile(enrollment.mac, wireguard.client_configuration(device.wireguard_peer), {
        "sip_server": str(WireGuardPeer.server_interface().ip), "sip_port": 5060,
        "sip_username": device.sip_username, "sip_password": device.sip_secret,
        "sip_extension": device.sip_extension, "transport": "UDP", "nat_traversal": "VPN",
        "codec": "PCMU", "dtmf": "RFC2833", "registration": True,
    })
    expires = now + timedelta(seconds=MAX_LEASE_SECONDS)
    save(enrollment, profile_expires_at=expires)
    atomic_private_file(profile_path(enrollment), json.dumps({
        "id": enrollment.pk.hex, "mac": enrollment.mac.lower(),
        "created": now.timestamp(), "expires": expires.timestamp(),
        "auth": password_digest(auth["username"], auth["password"]), "xml": base64.b64encode(xml).decode(),
    }))


def receipt_time(enrollment, now):
    try:
        path = Path(settings.PHONE_RECEIPT_DIR) / (enrollment.pk.hex + ".json")
        with path.open("rb") as f:
            data = json.loads(f.read(1024))
        at = timezone.datetime.fromtimestamp(data["at"], tz=timezone.get_current_timezone())
        if data["id"] == enrollment.pk.hex and enrollment.firmware_verified_at <= at <= now:
            return at
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        pass
    return None


class EnrollmentWorker:
    def __init__(self, client=None, clock=timezone.now, contact_check=contacts_available, apply=apply_asterisk_configuration):
        self.client = client or GDMSClient(GDMSSettings.from_django())
        self.clock, self.contact_check, self.apply = clock, contact_check, apply

    def step(self, enrollment):
        # HTTP only records removal intent. Refresh here so an already-selected
        # work item cannot restart provisioning after a removal request.
        enrollment.refresh_from_db()
        now = self.clock()
        # Next attempt is durable even if the process dies in a provider call.
        save(enrollment, next_attempt_at=now + timedelta(seconds=15))
        if enrollment.deregistering:
            from .deregistration_worker import DeregistrationWorker
            DeregistrationWorker(self.client, self.apply).step(enrollment, now)
            return
        if enrollment.state in TERMINAL:
            revoke_profile(enrollment)
            if enrollment.state == State.READY:
                self.retire(enrollment)
            return
        actor = Parent.objects.filter(pk=enrollment.requested_by_id, family_id=enrollment.family_id,
            is_guardian=True, user__is_active=True).exists()
        if not actor or (enrollment.assigned_parent_id and enrollment.assigned_parent.family_id != enrollment.family_id) or (enrollment.assigned_child_id and enrollment.assigned_child.family_id != enrollment.family_id):
            help_needed(enrollment, "access")
            return
        if enrollment.device_id:
            device = enrollment.device
            if (not device.is_active or not device.wireguard_peer_id or not device.wireguard_peer.is_active
                    or device.owning_family.pk != enrollment.family_id
                    or device.assigned_child_id != enrollment.assigned_child_id
                    or device.assigned_parent_id != enrollment.assigned_parent_id):
                help_needed(enrollment, "access")
                return
        if enrollment.org_id is None:
            save(enrollment, org_id=positive_id(settings.GDMS_ORG_ID), site_id=positive_id(settings.GDMS_SITE_ID))
        if not enrollment.gdms_added_at:
            self.enroll(enrollment, now)
            return
        row = self.client.device(enrollment.mac, enrollment.org_id)
        if not owned_inventory(enrollment, row):
            help_needed(enrollment, "ownership")
            return
        if row.get("deviceType") != "WP816":
            help_needed(enrollment, "model")
            return
        if enrollment.state == State.CONNECTING:
            self.connect(enrollment, now)
            return
        if enrollment.state == State.CONFIGURING:
            self.configure(enrollment, now)
            return
        # A numeric online inventory flag is only a hint to start a fresh read.
        if row.get("status") != 1:
            save(enrollment, next_attempt_at=now + timedelta(seconds=60))
            return
        if not enrollment.detail_started_at or now - enrollment.detail_started_at >= timedelta(seconds=60):
            save(enrollment, detail_started_at=now, state=State.UPGRADING if enrollment.operations.filter(kind="upgrade").exists() else State.FIRMWARE)
            self.client.live_device(enrollment.mac, first=True)
            return
        detail = self.client.live_device(enrollment.mac, first=False)
        if not detail:
            return
        if str(detail.get("sn", "")).upper() != enrollment.serial:
            help_needed(enrollment, "identity")
            return
        version = detail.get("softwareVersion", "")
        if not isinstance(version, str) or not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", version):
            help_needed(enrollment, "firmware")
            return
        save(enrollment, firmware_version=version, detail_started_at=None)
        if version == TARGET_FIRMWARE:
            save(enrollment, firmware_verified_at=now, state=State.CONFIGURING)
            return
        if tuple(map(int, version.split("."))) > tuple(map(int, TARGET_FIRMWARE.split("."))):
            help_needed(enrollment, "firmware")  # Never downgrade new stock automatically.
            return
        save(enrollment, state=State.UPGRADING)
        self.upgrade(enrollment, now)

    def enroll(self, enrollment, now):
        row = self.client.device(enrollment.mac, enrollment.org_id)
        entry = enrollment.operations.filter(kind="add").first()
        if row:
            # A device already present before our intent isn't our claim.
            if not entry or not owned_inventory(enrollment, row):
                help_needed(enrollment, "ownership")
            elif row.get("deviceType") != "WP816":
                help_needed(enrollment, "model")
            else:
                save(enrollment, gdms_added_at=now, state=State.WIFI)
            return
        if entry:
            if entry.status == "rejected" or now - entry.created_at > timedelta(minutes=5):
                help_needed(enrollment, "identity")
            return
        operation(enrollment, "add", lambda: self.client.add_device(mac=enrollment.mac, serial=enrollment.serial,
            device_name=enrollment.provider_name, org_id=enrollment.org_id, site_id=enrollment.site_id))
        # Reconcile exact inventory identity on the next step before moving on.

    def upgrade(self, enrollment, now):
        entry = enrollment.operations.filter(kind="upgrade").first()
        if entry:
            if entry.status == "rejected" or now - entry.created_at > timedelta(minutes=30):
                help_needed(enrollment, "upgrade_timeout")
            return
        verify_firmware_download(settings.WP816_FIRMWARE_URL)
        operation(enrollment, "upgrade", lambda: self.client.upgrade(mac=enrollment.mac, org_id=enrollment.org_id,
            task_name="fp-fw-" + enrollment.pk.hex, firmware_url=settings.WP816_FIRMWARE_URL))

    def configure(self, enrollment, now):
        entry = enrollment.operations.filter(kind="bootstrap").first()
        if entry:
            if entry.status == "rejected":
                help_needed(enrollment, "service")
            else:
                save(enrollment, state=State.CONNECTING)
            return
        # Do not release secrets based on an old or cached observation.
        if not enrollment.firmware_verified_at or now - enrollment.firmware_verified_at > timedelta(minutes=2):
            save(enrollment, state=State.FIRMWARE, detail_started_at=None)
            return
        allocate_phone(enrollment)
        if not enrollment.pbx_applied_at:
            self.apply(reload=True)
            save(enrollment, pbx_applied_at=now)
        publish_profile(enrollment, now)
        auth = credentials(enrollment)
        url = settings.PHONE_PROFILE_PUBLIC_URL.rstrip("/") + "/" + enrollment.pk.hex
        operation(enrollment, "bootstrap", lambda: self.client.configure_xml(mac=enrollment.mac, org_id=enrollment.org_id,
            xml=wp816.bootstrap_profile(enrollment.mac, url, auth["username"], auth["password"])))
        save(enrollment, state=State.CONNECTING)

    def connect(self, enrollment, now):
        if not enrollment.device_id or not enrollment.profile_expires_at:
            help_needed(enrollment, "service")
            return
        fetched = receipt_time(enrollment, now)
        if fetched and not enrollment.profile_downloaded_at:
            save(enrollment, profile_downloaded_at=fetched)
        peer = enrollment.device.wireguard_peer
        if (enrollment.profile_downloaded_at and peer.is_active and enrollment.device.is_active
                and peer.last_handshake_at and now - timedelta(minutes=3) <= peer.last_handshake_at <= now
                and peer.last_handshake_at >= enrollment.firmware_verified_at
                and self.contact_check(enrollment.device.sip_username)):
            revoke_profile(enrollment)
            save(enrollment, state=State.READY, connected_at=now, problem="", encrypted_bootstrap="")
            FamilyActivity.objects.create(family=enrollment.family, actor=None,
                description=f"Phone connected and ready for a test call: {enrollment.friendly_name}.")
            self.retire(enrollment)
        elif now >= enrollment.profile_expires_at:
            help_needed(enrollment, "delivery_timeout")

    def retire(self, enrollment):
        operation(enrollment, "retire", lambda: self.client.configure_xml(mac=enrollment.mac, org_id=enrollment.org_id,
            xml=wp816.disable_provisioning(enrollment.mac)))
