"""Private file-driven WireGuard runtime; no HTTP API or Docker socket.

Run only as the dedicated Compose service. All command arguments are fixed or
validated data. Command output, peer keys, and configuration are never logged.
"""

import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from .vpn_config import ServerConfig, VPNConfigurationError, firewall_config, parse_snapshot, wireguard_config


CONFIG = Path("/etc/frontporch-vpn")
DESIRED = Path("/var/lib/frontporch-vpn-desired")
OBSERVED = Path("/var/lib/frontporch-vpn")
RUNTIME = Path("/run/frontporch-vpn")


class VPNRuntimeError(RuntimeError):
    pass


def command(args, *, input=None):
    try:
        return subprocess.run(args, input=input, text=True, capture_output=True,
                              check=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        raise VPNRuntimeError("VPN system command failed; no command output was logged.") from None


def read_json(path):
    try:
        with path.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError
        return json.loads(data)
    except (OSError, ValueError, UnicodeError):
        raise VPNConfigurationError("Cannot read the bounded VPN configuration file.") from None


def atomic_private_file(path, content):
    """Readers see a complete snapshot. Never create public intermediate files."""
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def verify_namespace(server):
    if not Path("/.dockerenv").is_file() or os.environ.get("FRONTPORCH_VPN_CONTAINER") != "1":
        raise VPNRuntimeError("Start WireGuard only through its dedicated container service.")
    try:
        interfaces = json.loads(command(["ip", "-j", "-4", "address", "show", "scope", "global"]))
        addresses = [(row["ifname"], entry["local"]) for row in interfaces for entry in row["addr_info"]]
        if addresses != [("eth0", str(server.egress_address))]:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise VPNRuntimeError("Unexpected network namespace; no firewall changes were made.") from None
    for path in ("/proc/sys/net/ipv6/conf/all/disable_ipv6", "/proc/sys/net/ipv4/ip_forward"):
        if Path(path).read_text().strip() != "1":
            raise VPNRuntimeError("The VPN container requires IPv4 forwarding and disabled IPv6.")


def install_firewall(server):
    # Probe both tables before choosing a backend. New kernels may support the
    # legacy filter table but omit legacy NAT. Prefer legacy on the existing
    # host, and use nft only when the legacy probes fail. These commands run
    # after namespace verification and before creating the WireGuard interface.
    for backend in ("legacy", "nft"):
        try:
            for table in ("filter", "nat"):
                command([f"iptables-{backend}", "--wait", "5", "-t", table, "-S"])
        except VPNRuntimeError:
            continue
        # Never switch backends after a partial rule application. A restore
        # failure stops startup with no WireGuard interface accepting traffic.
        command([f"iptables-{backend}-restore", "--wait", "5"], input=firewall_config(server))
        print("VPN firewall backend: " + backend, flush=True)
        return
    raise VPNRuntimeError("No supported firewall backend provides both filter and NAT tables.")


def apply_peers(server, peers):
    path = RUNTIME / "wg.conf"
    try:
        atomic_private_file(path, wireguard_config(server, peers))
        command(["wg", "syncconf", "wg0", str(path)])
    finally:
        path.unlink(missing_ok=True)


def status(snapshot, *, now, state):
    # Avoid `wg show dump`: it includes private and preshared keys.
    rows = command(["wg", "show", "wg0", "latest-handshakes"]).splitlines()
    handshakes = {}
    for row in rows:
        parts = row.split()
        if len(parts) == 2 and parts[1].isdigit():
            handshakes[parts[0]] = int(parts[1])
    return {"schema": 1, "observed_at": now, "state": state,
            "revision": snapshot.revision if snapshot else None,
            "peers": [{"id": peer.id, "latest_handshake": handshakes.get(peer.public_key, 0)}
                      for peer in snapshot.peers] if snapshot else []}


def run():
    os.umask(0o077)
    server = ServerConfig.parse(read_json(CONFIG / "server.json"))
    verify_namespace(server)
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    OBSERVED.mkdir(parents=True, exist_ok=True, mode=0o700)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    interface_created = False
    try:
        install_firewall(server)
        command(["ip", "link", "add", "wg0", "type", "wireguard"])
        interface_created = True
        command(["ip", "address", "add", str(server.address), "dev", "wg0"])
        command(["ip", "link", "set", "dev", "wg0", "mtu", str(server.mtu)])
        apply_peers(server, ())
        command(["ip", "link", "set", "up", "dev", "wg0"])
        previous, last_generated = None, 0
        last_state = None
        while not stopping:
            now = time.time()
            try:
                snapshot = parse_snapshot(read_json(DESIRED / "peers.json"), server, now)
                if snapshot.generated_at < last_generated:
                    raise VPNConfigurationError("Older peer snapshot rejected.")
                last_generated = snapshot.generated_at
                state = "active"
            except VPNConfigurationError:
                snapshot, state = None, "no_valid_snapshot"
            peers = snapshot.peers if snapshot else ()
            if peers != previous:
                apply_peers(server, peers)
                previous = peers
            atomic_private_file(OBSERVED / "status.json", json.dumps(status(snapshot, now=now, state=state)))
            if state != last_state:
                print("VPN state: " + state, flush=True)
                last_state = state
            for _ in range(5):
                if stopping:
                    break
                time.sleep(1)
    finally:
        if interface_created:
            # Revocation remains effective even if status publication fails.
            command(["ip", "link", "delete", "wg0"])


def healthy():
    try:
        record = read_json(OBSERVED / "status.json")
        return record.get("state") == "active" and 0 <= time.time() - record["observed_at"] < 20
    except (VPNConfigurationError, KeyError, TypeError):
        return False


if __name__ == "__main__":
    try:
        run()
    except (VPNConfigurationError, VPNRuntimeError, OSError):
        raise SystemExit("VPN service stopped safely; inspect private operator configuration.") from None
