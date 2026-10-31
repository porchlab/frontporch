"""Disposable Linux-kernel integration test. No host ports or production data.

Build `docker build --target network-tools -t frontporch-vpn-test-tools:local .`
then run `uv run python deploy/test_wireguard_network.py` on a Docker Linux VM.
"""

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get("FRONTPORCH_VPN_TEST_IMAGE", "frontporch-vpn-test-tools:local")


def docker(*args, input=None):
    result = subprocess.run(["docker", *args], input=input, text=True, capture_output=True, timeout=45)
    if result.returncode:
        # Fixture private keys also stay out of failure logs.
        raise RuntimeError(f"Docker integration step failed: {args[0]}")
    return result.stdout.strip()


def keys():
    private = docker("run", "--rm", "--network", "none", "--cap-drop", "ALL", IMAGE, "wg", "genkey")
    public = docker("run", "--rm", "-i", "--network", "none", "--cap-drop", "ALL", IMAGE, "wg", "pubkey",
                    input=private + "\n")
    return private, public


def write_json(path, value):
    temporary = path.with_suffix(".new")
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


ECHO = """import socket,threading,time
def echo(port):
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('0.0.0.0',port))
 while True:
  data,addr=s.recvfrom(1024);s.sendto(data,addr)
for port in (5060,15000,9999,9000):threading.Thread(target=echo,args=(port,),daemon=True).start()
while True:time.sleep(1)
"""
CLIENT = """import subprocess,os
def run(*args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
run('ip','link','add','wg0','type','wireguard')
run('ip','address','add',os.environ['CLIENT_ADDRESS']+'/32','dev','wg0')
run('wg','setconf','wg0','/fixture/client.conf')
run('ip','link','set','up','dev','wg0')
for route in ('10.240.191.0/29','10.240.190.3/32','10.240.190.6/32'):
 run('ip','route','add',route,'dev','wg0')
exec(open('/fixture/echo.py').read())
"""
PROBE = """import socket,sys
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(1)
s.bind((sys.argv[1],0));s.sendto(b'fixture-echo',(sys.argv[2],int(sys.argv[3])))
try:print('received' if s.recv(1024)==b'fixture-echo' else 'wrong')
except TimeoutError:print('blocked')
"""


def main():
    # Native Linux bind mounts retain the runner's UID/GID. With all capabilities
    # dropped, container root cannot bypass a runner-owned 0700/0600 fixture.
    # Share only the runner group with these disposable containers; production
    # artifacts remain root-owned 0700/0600. No DAC override capability is needed.
    os.umask(0o007)
    fixture_group = str(os.getgid())
    prefix = "frontporch-vpn-test-" + uuid.uuid4().hex[:10]
    containers = []
    network_created = False
    (ROOT / ".local").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vpn-network-", dir=ROOT / ".local") as temporary:
        directory = Path(temporary)
        desired, observed, package, config = [directory / name for name in ("desired", "observed", "frontporch", "config")]
        for path in (desired, observed, package, config):
            path.mkdir()
        for filename in ("__init__.py", "vpn_config.py", "vpn_runtime.py"):
            shutil.copyfile(ROOT / "frontporch" / filename, package / filename)
        (directory / "echo.py").write_text(ECHO)
        server_private, server_public = keys()
        client_keys = [keys(), keys()]
        psk = base64.b64encode(os.urandom(32)).decode()
        server = {"address": "10.240.191.1/29", "egress_address": "10.240.190.2",
                  "pbx_address": "10.240.190.3", "private_key": server_private,
                  "listen_port": 51821, "sip_port": 5060, "rtp_start": 10000, "rtp_end": 20000, "mtu": 1380}
        peers = [{"id": str(uuid.uuid4()), "address": f"10.240.191.{index + 2}",
                  "public_key": public, "preshared_key": "" if index == 0 else psk,
                  "persistent_keepalive": 25}
                 for index, (_, public) in enumerate(client_keys)]

        def publish(rows, *, expired=False):
            now = time.time()
            write_json(desired / "peers.json", {"schema": 1, "revision": str(uuid.uuid4()),
                       "generated_at": now - 100 if expired else now,
                       "expires_at": now - 1 if expired else now + 300, "peers": rows})

        def wait_for(predicate, message):
            for _ in range(60):
                if predicate():
                    return
                time.sleep(0.25)
            raise AssertionError(message)

        def peer_count():
            return len(docker("exec", prefix + "-server", "wg", "show", "wg0", "peers").splitlines())

        def probe(index, target, port):
            return docker("exec", prefix + f"-client{index}", "python", "-c", PROBE,
                          peers[index]["address"], target, str(port))

        try:
            docker("network", "create", "--internal", "--subnet", "10.240.190.0/29", prefix)
            network_created = True
            write_json(config / "server.json", server)
            publish(peers)
            for suffix, ip in (("pbx", "10.240.190.3"), ("other-lan", "10.240.190.6")):
                name = prefix + "-" + suffix
                docker("run", "-d", "--name", name, "--network", prefix, "--ip", ip,
                       "--group-add", fixture_group,
                       "--cap-drop", "ALL", "--read-only", "--security-opt", "no-new-privileges",
                       "--mount", f"type=bind,src={directory / 'echo.py'},dst=/echo.py,readonly",
                       IMAGE, "python", "/echo.py")
                containers.append(name)
            name = prefix + "-server"
            docker("run", "-d", "--name", name, "--network", prefix, "--ip", "10.240.190.2",
                   "--group-add", fixture_group,
                   "--cap-drop", "ALL", "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW",
                   "--read-only", "--security-opt", "no-new-privileges",
                   "--sysctl", "net.ipv4.ip_forward=1", "--sysctl", "net.ipv6.conf.all.disable_ipv6=1",
                   "--sysctl", "net.ipv6.conf.default.disable_ipv6=1",
                   "--tmpfs", "/run:rw,noexec,nosuid,nodev,size=4m", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=4m",
                   "-e", "FRONTPORCH_VPN_CONTAINER=1", "--mount", f"type=bind,src={package},dst=/app/frontporch,readonly",
                   "--mount", f"type=bind,src={config},dst=/etc/frontporch-vpn,readonly",
                   "--mount", f"type=bind,src={desired},dst=/var/lib/frontporch-vpn-desired,readonly",
                   "--mount", f"type=bind,src={observed},dst=/var/lib/frontporch-vpn",
                   IMAGE, "python", "-m", "frontporch.vpn_runtime")
            containers.append(name)
            wait_for(lambda: (observed / "status.json").exists(), "VPN runtime did not become ready")
            for index, (private, _) in enumerate(client_keys):
                fixture = directory / f"client{index}"
                fixture.mkdir()
                (fixture / "client.py").write_text(CLIENT)
                (fixture / "echo.py").write_text(ECHO)
                (fixture / "client.conf").write_text(
                    f"[Interface]\nPrivateKey = {private}\n[Peer]\nPublicKey = {server_public}\n"
                    + (f"PresharedKey = {psk}\n" if index else "")
                    + "Endpoint = 10.240.190.2:51821\nAllowedIPs = 10.240.191.0/29,10.240.190.3/32,10.240.190.6/32\nPersistentKeepalive = 25\n")
                name = prefix + f"-client{index}"
                docker("run", "-d", "--name", name, "--network", prefix, "--ip", f"10.240.190.{index+4}",
                       "--group-add", fixture_group,
                       "--cap-drop", "ALL", "--cap-add", "NET_ADMIN", "--read-only",
                       "--security-opt", "no-new-privileges", "--mount", f"type=bind,src={fixture},dst=/fixture,readonly",
                       "-e", f"CLIENT_ADDRESS={peers[index]['address']}", IMAGE, "python", "/fixture/client.py")
                containers.append(name)
            wait_for(lambda: probe(0, "10.240.191.1", 5060) == "received", "Legacy peer did not reach PBX")
            for index in (0, 1):
                assert probe(index, "10.240.191.1", 5060) == "received"
                assert probe(index, "10.240.191.1", 15000) == "received"
                assert probe(index, "10.240.191.1", 9999) == "blocked"
                assert probe(index, "10.240.190.3", 9999) == "blocked"
                assert probe(index, "10.240.190.6", 5060) == "blocked"
                assert probe(index, peers[1-index]["address"], 9000) == "blocked"
            print("PASS: legacy and managed peers reach SIP/RTP; other ports, LAN, and peer traffic are denied.", flush=True)
            publish(peers[1:])
            wait_for(lambda: peer_count() == 1, "Revoked peer was not removed")
            assert probe(0, "10.240.191.1", 5060) == "blocked"
            assert probe(1, "10.240.191.1", 5060) == "received"
            print("PASS: revocation removes one peer without interrupting the other.", flush=True)
            publish(peers[1:], expired=True)
            wait_for(lambda: peer_count() == 0, "Expired snapshot did not remove peers")
            assert probe(1, "10.240.191.1", 5060) == "blocked"
            print("PASS: expired control-plane state fails closed.", flush=True)
        except Exception:
            # Only disposable fixture containers, never production logs. Include
            # startup diagnostics while still removing every generated key.
            redactions = [server_private, server_public, psk,
                          *[value for pair in client_keys for value in pair]]
            for name in containers:
                result = subprocess.run(["docker", "logs", name], capture_output=True, text=True, timeout=10)
                output = result.stdout + result.stderr
                for value in redactions:
                    output = output.replace(value, "[redacted fixture key]")
                print(f"Fixture {name.removeprefix(prefix + '-')}: {output[-2000:]}", flush=True)
            raise
        finally:
            for name in reversed(containers):
                subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if network_created:
                subprocess.run(["docker", "network", "rm", prefix], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
