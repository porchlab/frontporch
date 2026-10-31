"""Family-owned peers: imports, recoverable secrets, and desired server state.

This module has no remote administration API. A private worker publishes bounded
snapshots to the isolated container; revocation does not depend on GDMS support.
"""

import base64
import configparser
import ipaddress
import json
import os
import time
import uuid
import re
from urllib.parse import urlsplit
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.views.decorators.debug import sensitive_variables

from frontporch.vpn_config import ServerConfig, VPNConfigurationError, key, parse_snapshot
from frontporch.vpn_runtime import atomic_private_file, read_json
from .models import Device, Family, FamilyActivity, WireGuardPeer, lock_extension_namespace


def cipher():
    try:
        return Fernet(settings.WIREGUARD_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError, AttributeError):
        raise ImproperlyConfigured("Configure a dedicated WIREGUARD_ENCRYPTION_KEY in the private environment.") from None


@sensitive_variables()
def seal_secrets(peer, *, private_key="", preshared_key=""):
    if private_key:
        raw = base64.b64decode(key(private_key))
        derived = base64.b64encode(X25519PrivateKey.from_private_bytes(raw).public_key().public_bytes_raw()).decode()
        if derived != peer.public_key:
            raise VPNConfigurationError("Client private key does not match this peer.")
    if preshared_key:
        key(preshared_key)
    return cipher().encrypt(json.dumps({"peer_id": str(peer.pk), "public_key": peer.public_key,
                                       "private_key": private_key, "preshared_key": preshared_key}).encode()).decode()


@sensitive_variables()
def peer_secrets(peer):
    if not peer.encrypted_secrets:
        return {"private_key": "", "preshared_key": ""}
    try:
        data = json.loads(cipher().decrypt(peer.encrypted_secrets.encode()))
        if (not isinstance(data, dict) or set(data) != {"peer_id", "public_key", "private_key", "preshared_key"}
                or data["peer_id"] != str(peer.pk) or data["public_key"] != peer.public_key):
            raise ValueError
        for field in ("private_key", "preshared_key"):
            if data[field]:
                key(data[field])
        return {field: data[field] for field in ("private_key", "preshared_key")}
    except (InvalidToken, ValueError, TypeError, KeyError, UnicodeError):
        raise VPNConfigurationError("Cannot decrypt the secrets for this peer.") from None


@sensitive_variables()
def generate_peer_keys(peer):
    private = X25519PrivateKey.generate()
    peer.public_key = base64.b64encode(private.public_key().public_bytes_raw()).decode()
    peer.encrypted_secrets = seal_secrets(
        peer, private_key=base64.b64encode(private.private_bytes_raw()).decode(),
        preshared_key=base64.b64encode(os.urandom(32)).decode(),
    )


@sensitive_variables()
def client_configuration(peer):
    secrets = peer_secrets(peer)
    if not peer.is_active or not secrets["private_key"]:
        raise ValidationError("This connection has no downloadable active client configuration. Imported clients keep their existing files.")
    endpoint = getattr(settings, "WIREGUARD_ENDPOINT", "")
    try:
        parsed = urlsplit("udp://" + endpoint)
        if (not parsed.hostname or not parsed.port or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment
                or not re.fullmatch(r"[A-Za-z0-9.:[\]-]+", endpoint)):
            raise ValueError
        public = key(settings.WIREGUARD_SERVER_PUBLIC_KEY)
    except (ValueError, AttributeError):
        raise ImproperlyConfigured("Configure the WireGuard server public key and public UDP endpoint.") from None
    lines = ["[Interface]", f"PrivateKey = {secrets['private_key']}",
             f"Address = {peer.client_address}/32", "MTU = 1380", "", "[Peer]",
             f"PublicKey = {public}", f"Endpoint = {endpoint}",
             f"AllowedIPs = {peer.server_interface().ip}/32", "PersistentKeepalive = 25"]
    if secrets["preshared_key"]:
        lines.append(f"PresharedKey = {secrets['preshared_key']}")
    return "\n".join(lines) + "\n"


def audit(peer, actor, description):
    FamilyActivity.objects.create(family=peer.family, actor=actor, description=description,
                                  details={"wireguard_peer_id": str(peer.pk),
                                           "provisioning_method": peer.provisioning_method,
                                           "is_active": peer.is_active})


@transaction.atomic
@sensitive_variables()
def create_peer(*, family, name, provisioning_method, actor=None):
    """Trusted callers authorize the family before requesting fresh credentials."""
    peer = WireGuardPeer(family=family, name=name, provisioning_method=provisioning_method)
    generate_peer_keys(peer)
    peer.save()
    audit(peer, actor, f"Added network connection: {peer.name}.")
    return peer


@sensitive_variables()
def parse_legacy_config(text):
    """Parse `wg showconf`, never execute hooks or import changing WAN endpoints.

    Current legacy peers each have one /32. Reject wider routed networks for
    explicit operator review rather than silently dropping or widening routes.
    """
    if not isinstance(text, str) or len(text) > 1024 * 1024:
        raise VPNConfigurationError("Invalid legacy configuration size.")
    interface, peers, section = None, [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[Interface]" and interface is None and not peers:
            interface = section = {}
        elif line == "[Peer]" and interface is not None:
            section = {}
            peers.append(section)
        elif section is not None and "=" in line:
            name, value = (part.strip() for part in line.split("=", 1))
            if name in section:
                raise VPNConfigurationError("Duplicate legacy option.")
            section[name] = value
        else:
            raise VPNConfigurationError("Invalid legacy configuration syntax.")
    if (interface is None or set(interface) - {"PrivateKey", "ListenPort", "FwMark"}
            or not {"PrivateKey", "ListenPort"} <= set(interface) or len(peers) > 4096):
        raise VPNConfigurationError("Unsupported legacy interface settings.")
    private = key(interface["PrivateKey"])
    if interface.get("FwMark", "0") not in ("0", "off", "0x0"):
        raise VPNConfigurationError("Legacy firewall marks require operator review.")
    try:
        port = int(interface["ListenPort"])
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise VPNConfigurationError("Invalid legacy listen port.") from None
    result, addresses, keys = [], set(), set()
    for peer in peers:
        if set(peer) - {"PublicKey", "PresharedKey", "AllowedIPs", "Endpoint", "PersistentKeepalive"}:
            raise VPNConfigurationError("Unsupported legacy peer setting.")
        try:
            address = ipaddress.IPv4Network(peer.get("AllowedIPs", ""))
            keepalive = int(peer.get("PersistentKeepalive", "0"))
            if address.prefixlen != 32 or not 0 <= keepalive <= 65535:
                raise ValueError
        except ValueError:
            raise VPNConfigurationError("Legacy peers require one IPv4 host route and a valid keepalive.") from None
        public = key(peer.get("PublicKey"))
        psk = key(peer["PresharedKey"]) if peer.get("PresharedKey") else ""
        if public in keys or address in addresses:
            raise VPNConfigurationError("Duplicate legacy peer key or address.")
        keys.add(public)
        addresses.add(address)
        result.append({"public_key": public, "client_address": str(address.network_address),
                       "preshared_key": psk, "persistent_keepalive": keepalive})
    return {"private_key": private, "listen_port": port, "peers": result}


@sensitive_variables()
def imported_client_keys(legacy, texts):
    """Optional known client files; legacy peers need no client private key."""
    server_private = X25519PrivateKey.from_private_bytes(base64.b64decode(legacy["private_key"]))
    server_public = base64.b64encode(server_private.public_key().public_bytes_raw()).decode()
    peers = {row["public_key"]: row for row in legacy["peers"]}
    result = {}
    if not isinstance(texts, list) or len(texts) > len(peers):
        raise VPNConfigurationError("Invalid client configuration count.")
    for text in texts:
        if not isinstance(text, str) or len(text) > 16384:
            raise VPNConfigurationError("Invalid client configuration size.")
        config = configparser.ConfigParser(interpolation=None, strict=True)
        config.optionxform = str
        try:
            config.read_string(text)
            if config.defaults() or set(config.sections()) != {"Interface", "Peer"}:
                raise ValueError
            interface, remote = config["Interface"], config["Peer"]
            if (set(interface) - {"PrivateKey", "Address", "DNS", "MTU", "ListenPort"}
                    or set(remote) - {"PublicKey", "PresharedKey", "Endpoint", "AllowedIPs", "PersistentKeepalive"}):
                raise ValueError
            private = key(interface.get("PrivateKey"))
            public = base64.b64encode(X25519PrivateKey.from_private_bytes(
                base64.b64decode(private)).public_key().public_bytes_raw()).decode()
            address = str(ipaddress.IPv4Interface(interface.get("Address", "")).ip)
            source = peers[public]
            if (public in result or source["client_address"] != address
                    or remote.get("PublicKey") != server_public
                    or remote.get("PresharedKey", "") != source["preshared_key"]):
                raise ValueError
        except (configparser.Error, ValueError, KeyError, TypeError):
            raise VPNConfigurationError("Client configuration does not match an imported peer and server identity.") from None
        result[public] = private
    return result


@transaction.atomic
@sensitive_variables()
def import_peers(legacy, assignments, *, actor=None, apply=False, client_keys=None):
    """All-or-nothing import with an explicit family assignment for every peer."""
    lock_extension_namespace()
    client_keys = client_keys or {}
    if not isinstance(assignments, list) or len(assignments) != len(legacy["peers"]):
        raise ValidationError("Provide one family assignment for every imported peer.")
    by_address = {}
    for row in assignments:
        required = {"client_address", "family_id", "name", "provisioning_method"}
        if (not isinstance(row, dict) or not required <= set(row) or set(row) - required - {"device_ids"}
                or not isinstance(row["client_address"], str)):
            raise ValidationError("Invalid peer family assignment.")
        if row["client_address"] in by_address:
            raise ValidationError("Duplicate peer family assignment.")
        by_address[row["client_address"]] = row
    peers, phone_assignments, family_names, assigned_devices = [], [], set(), set()
    for source in legacy["peers"]:
        row = by_address.get(source["client_address"])
        if row is None or type(row["family_id"]) is not int:
            raise ValidationError("Every peer must have an explicit existing family.")
        try:
            family = Family.objects.get(pk=row["family_id"])
        except Family.DoesNotExist:
            raise ValidationError("An assigned family does not exist.") from None
        peer = WireGuardPeer(family=family, name=row["name"], provisioning_method=row["provisioning_method"],
                             public_key=source["public_key"], client_address=source["client_address"],
                             persistent_keepalive=source["persistent_keepalive"])
        private = client_keys.get(source["public_key"], "")
        if peer.provisioning_method == WireGuardPeer.Provisioning.GDMS and not private:
            raise ValidationError("GDMS provisioning requires the matching client configuration; otherwise import the peer as manual.")
        if source["preshared_key"] or private:
            peer.encrypted_secrets = seal_secrets(peer, private_key=private, preshared_key=source["preshared_key"])
        peer.full_clean()
        identity = (peer.family_id, peer.name)
        if identity in family_names:
            raise ValidationError("Duplicate connection name within a family.")
        family_names.add(identity)
        device_ids = row.get("device_ids", [])
        if (not isinstance(device_ids, list) or any(type(pk) is not int for pk in device_ids)
                or len(set(device_ids)) != len(device_ids)
                or (peer.provisioning_method == WireGuardPeer.Provisioning.GDMS and len(device_ids) > 1)):
            raise ValidationError("Invalid phone assignments for the connection.")
        devices = list(Device.objects.filter(pk__in=device_ids).select_related(
            "assigned_child__family", "assigned_parent__family", "assigned_family"))
        if len(devices) != len(device_ids) or any(
            device.owning_family.pk != peer.family_id or device.wireguard_peer_id
            or device.pk in assigned_devices for device in devices
        ):
            raise ValidationError("Phones must belong to the assigned family and have no existing peer assignment.")
        assigned_devices.update(device_ids)
        peers.append(peer)
        phone_assignments.append(devices)
    if apply:
        for peer, devices in zip(peers, phone_assignments):
            peer.save()
            for device in devices:
                device.wireguard_peer = peer
                device.save(update_fields=["wireguard_peer", "updated_at"])
            audit(peer, actor, f"Imported existing network connection: {peer.name}.")
    return peers


@transaction.atomic
@sensitive_variables()
def desired_snapshot(server, *, now=None):
    lock_extension_namespace()
    if server.address != WireGuardPeer.server_interface():
        raise VPNConfigurationError("Django and the server must use the same VPN subnet and address.")
    now = time.time() if now is None else now
    peers = [{"id": str(peer.pk), "address": peer.client_address, "public_key": peer.public_key,
              "preshared_key": peer_secrets(peer)["preshared_key"],
              "persistent_keepalive": peer.persistent_keepalive}
             for peer in WireGuardPeer.objects.filter(is_active=True).order_by("client_address", "pk")]
    data = {"schema": 1, "revision": str(uuid.uuid4()), "generated_at": now, "expires_at": now + 300,
            "peers": peers}
    parse_snapshot(data, server, now)
    return data


@transaction.atomic
@sensitive_variables()
def reconcile_once():
    if not settings.WIREGUARD_ENABLED:
        raise ImproperlyConfigured("WIREGUARD_ENABLED must be explicitly enabled for the private reconciler.")
    if not settings.WIREGUARD_DESIRED_DIR or not settings.WIREGUARD_OBSERVED_DIR or not settings.WIREGUARD_NETWORK_FILE:
        raise ImproperlyConfigured("Configure the private desired and observed WireGuard directories.")
    # Serialize the complete read/publish cycle, including multiple workers.
    lock_extension_namespace()
    desired, observed = Path(settings.WIREGUARD_DESIRED_DIR), Path(settings.WIREGUARD_OBSERVED_DIR)
    server = ServerConfig.parse(read_json(Path(settings.WIREGUARD_NETWORK_FILE)), require_private_key=False)
    now = time.time()
    # Accept acknowledgements only for the current desired revision, never stale
    # status left from another run. Read before publishing the next revision.
    try:
        previous = parse_snapshot(read_json(desired / "peers.json"), server, now)
        report = read_json(observed / "status.json")
        if (report.get("revision") == previous.revision and report.get("state") == "active"
                and type(report.get("observed_at")) in (int, float)
                and 0 <= now - report["observed_at"] < 20):
            expected = {peer.id for peer in previous.peers}
            for row in report.get("peers", []):
                if row.get("id") not in expected or type(row.get("latest_handshake")) is not int:
                    continue
                last = row["latest_handshake"]
                if not 0 <= last <= now:
                    continue
                WireGuardPeer.objects.filter(pk=row["id"], is_active=True).update(
                    last_applied_at=datetime.fromtimestamp(report["observed_at"], datetime_timezone.utc),
                    last_handshake_at=datetime.fromtimestamp(last, datetime_timezone.utc) if last else None,
                )
    except (VPNConfigurationError, ValueError, TypeError, KeyError, AttributeError):
        pass
    data = desired_snapshot(server, now=now)
    atomic_private_file(desired / "peers.json", json.dumps(data))
    return len(data["peers"])
