"""Validated data formats for the isolated WireGuard container.

No Django, subprocesses, network access, or secret logging in this module.
Only the container runtime may apply the returned configuration.
"""

import base64
import ipaddress
import math
import uuid
from dataclasses import dataclass, field


class VPNConfigurationError(ValueError):
    pass


PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))


def private_address(value):
    try:
        address = ipaddress.IPv4Address(value)
        if not any(address in network for network in PRIVATE_NETWORKS):
            raise ValueError
        return address
    except (ValueError, TypeError):
        raise VPNConfigurationError("Expected a private IPv4 address.") from None


def key(value):
    try:
        decoded = base64.b64decode(value, validate=True)
        if (not isinstance(value, str) or len(decoded) != 32 or not any(decoded)
                or base64.b64encode(decoded).decode() != value):
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise VPNConfigurationError("Invalid WireGuard key.") from None


def integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise VPNConfigurationError("Invalid numeric VPN setting.")
    return value


@dataclass(frozen=True)
class ServerConfig:
    address: ipaddress.IPv4Interface
    egress_address: ipaddress.IPv4Address
    pbx_address: ipaddress.IPv4Address
    private_key: str = field(repr=False)
    listen_port: int = 51821
    sip_port: int = 5060
    rtp_start: int = 10000
    rtp_end: int = 20000
    mtu: int = 1380

    @classmethod
    def parse(cls, data, *, require_private_key=True):
        fields = {"address", "egress_address", "pbx_address", "private_key",
                  "listen_port", "sip_port", "rtp_start", "rtp_end", "mtu"}
        if not require_private_key:
            fields.remove("private_key")
        if not isinstance(data, dict) or set(data) != fields:
            raise VPNConfigurationError("Invalid server configuration fields.")
        try:
            address = ipaddress.IPv4Interface(data["address"])
        except (ValueError, TypeError):
            raise VPNConfigurationError("Invalid VPN subnet.") from None
        network = address.network
        if (not 16 <= network.prefixlen <= 29
                or not any(network.subnet_of(n) for n in PRIVATE_NETWORKS)
                or address.ip in (network.network_address, network.broadcast_address)):
            raise VPNConfigurationError("Use a private VPN subnet with usable host addresses.")
        egress, pbx = private_address(data["egress_address"]), private_address(data["pbx_address"])
        if egress == pbx or egress in network or pbx in network:
            raise VPNConfigurationError("The PBX and container bridge must be separate from the VPN subnet.")
        start, end = integer(data["rtp_start"], 1024, 65535), integer(data["rtp_end"], 1024, 65535)
        if end < start or end - start > 32767:
            raise VPNConfigurationError("Invalid PBX media port range.")
        return cls(address, egress, pbx, key(data["private_key"]) if require_private_key else "",
                   integer(data["listen_port"], 1024, 65535), integer(data["sip_port"], 1024, 65535),
                   start, end, integer(data["mtu"], 1280, 1500))


@dataclass(frozen=True)
class Peer:
    id: str
    address: ipaddress.IPv4Address
    public_key: str = field(repr=False)
    preshared_key: str = field(repr=False)
    persistent_keepalive: int = 0


@dataclass(frozen=True)
class Snapshot:
    revision: str
    generated_at: float
    expires_at: float
    peers: tuple[Peer, ...]


def identifier(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
        return value
    except (ValueError, TypeError, AttributeError):
        raise VPNConfigurationError("Invalid VPN record identifier.") from None


def parse_snapshot(data, server, now):
    if (not isinstance(data, dict)
            or set(data) != {"schema", "revision", "generated_at", "expires_at", "peers"}
            or type(data["schema"]) is not int or data["schema"] != 1):
        raise VPNConfigurationError("Invalid peer snapshot schema.")
    created, expires = data["generated_at"], data["expires_at"]
    if (type(created) not in (int, float) or type(expires) not in (int, float)
            or not math.isfinite(created) or not math.isfinite(expires)
            or not created <= now + 30 or not created < expires <= created + 3600
            or not now < expires):
        raise VPNConfigurationError("Peer snapshot is expired or has an invalid lifetime.")
    rows = data["peers"]
    if not isinstance(rows, list) or len(rows) > 4096:
        raise VPNConfigurationError("Invalid peer snapshot size.")
    peers, ids, addresses, keys = [], set(), set(), set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "address", "public_key", "preshared_key", "persistent_keepalive"}:
            raise VPNConfigurationError("Invalid peer fields.")
        peer_id, address = identifier(row["id"]), private_address(row["address"])
        public = key(row["public_key"])
        preshared = key(row["preshared_key"]) if row["preshared_key"] != "" else ""
        if (address not in server.address.network or address in (
                server.address.ip, server.address.network.network_address,
                server.address.network.broadcast_address)):
            raise VPNConfigurationError("Peer address is not an available VPN host.")
        if peer_id in ids or address in addresses or public in keys:
            raise VPNConfigurationError("Duplicate peer identity, address, or key.")
        ids.add(peer_id)
        addresses.add(address)
        keys.add(public)
        peers.append(Peer(peer_id, address, public, preshared, integer(row["persistent_keepalive"], 0, 65535)))
    return Snapshot(identifier(data["revision"]), created, expires,
                    tuple(sorted(peers, key=lambda peer: int(peer.address))))


def wireguard_config(server, peers):
    """wg syncconf removes missing peers while preserving unchanged sessions."""
    lines = ["[Interface]", f"PrivateKey = {key(server.private_key)}", f"ListenPort = {server.listen_port}"]
    for peer in sorted(peers, key=lambda peer: int(peer.address)):
        # An explicit zero key clears a previously configured PSK. Existing
        # QNAP clients without a PSK must keep working without client changes.
        psk = peer.preshared_key or base64.b64encode(bytes(32)).decode()
        lines.extend(["", "[Peer]", f"PublicKey = {peer.public_key}",
                      f"PresharedKey = {psk}", f"AllowedIPs = {peer.address}/32",
                      f"PersistentKeepalive = {peer.persistent_keepalive}"])
    return "\n".join(lines) + "\n"


def firewall_config(server):
    """Apply only inside the verified, dedicated network namespace.

    Phones reach only one PBX address over UDP SIP/RTP. No peer-to-peer, LAN,
    management, DNS, or Internet forwarding is allowed. NAT avoids host routes.
    """
    ports = f"{server.sip_port},{server.rtp_start}:{server.rtp_end}"
    return f"""*filter
:INPUT DROP [0:0]
:FORWARD DROP [0:0]
:OUTPUT ACCEPT [0:0]
-A INPUT -i lo -j ACCEPT
-A INPUT -i eth0 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
-A INPUT -i eth0 -p udp --dport {server.listen_port} -j ACCEPT
-A FORWARD -i wg0 -o eth0 -d {server.pbx_address}/32 -p udp -m multiport --dports {ports} -j ACCEPT
-A FORWARD -i eth0 -o wg0 -s {server.pbx_address}/32 -p udp -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
COMMIT
*nat
:PREROUTING ACCEPT [0:0]
:INPUT ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
:POSTROUTING ACCEPT [0:0]
-A PREROUTING -i wg0 -d {server.address.ip}/32 -p udp -m multiport --dports {ports} -j DNAT --to-destination {server.pbx_address}
-A POSTROUTING -s {server.address.network} -d {server.pbx_address}/32 -o eth0 -p udp -m multiport --dports {ports} -j MASQUERADE
COMMIT
"""
