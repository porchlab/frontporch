# Family WireGuard peers and staged server migration

## Status and ownership

The implementation includes family-owned peer records, private Django Admin
management, encrypted optional client secrets, legacy import, a private
reconciler, and an opt-in bridge-networked server. Kernel-level tests cover SIP/RTP
forwarding, peer/LAN isolation, revocation, and expired snapshots. Production
cutover and handset tests on this server are still required. The existing QNAP
service must remain available until the staged test succeeds.

A family can own any number of peers. Each peer has a name and either **Manual
configuration** or **GDMS provisioning**. A manual gateway can serve multiple
phones in that family; a GDMS peer represents one physical phone. A phone cannot
use another family's peer. Transfer requires removing its phone assignments.
GDMS controls handset delivery; it does not own the WireGuard server or determine
family ownership. Both kinds of peer appear in the same private admin list and
use the same revocation path.

Staff can add a peer with an existing public key or leave that field blank to
generate a new connection. Leaving the address blank allocates an unused address
under a database lock. New client keys and optional preshared keys are encrypted
with a dedicated Fernet key, bound to the peer's ID and public key. Staff with
change permission can download a known client configuration through the admin
action; the response is an attachment with `no-store`, and the download is audited.
Imported peers normally have no known client private key, so their existing
client files remain in use. GDMS mode requires a recoverable client key; import
the matching client file or generate a new connection before selecting it.
Revoked addresses are reserved until explicit deletion.

Private keys, preshared keys, and raw configuration never appear in admin lists,
audit details, or service logs. The public parent portal has no admin routes and
does not receive the peer encryption key. A family self-service enrollment page
and the GDMS firmware/onboarding worker remain separate, subsequent work.

## Container boundary

The server uses a dedicated Docker bridge and only `NET_ADMIN` and `NET_RAW` in its
own network namespace. The latter supports the host's legacy iptables control
socket. It has no host networking, privileged mode, Docker socket, host-root
mount, database connection, or management HTTP API. The host must already support
kernel WireGuard; no kernel modules are installed or mounted from the container.
Before changing firewall rules, the runtime verifies that it is in a container
with only the expected bridge interface/address, IPv4 forwarding, and disabled
IPv6. A failed check leaves the firewall untouched.

The firewall permits phones to reach only the PBX's UDP SIP port and configured
RTP range. It denies peer-to-peer traffic, other LAN destinations, management
ports, and Internet forwarding. It translates the old VPN server address to the
PBX's Docker bridge gateway and uses source NAT for replies. This avoids adding
host routes or exposing SIP publicly. The old VPN address can be retained inside
the isolated namespace while QNAP is still serving the original VPN.

Generated Asterisk endpoints for assigned peers advertise that VPN address for
media and send OPTIONS every 25 seconds to maintain legacy SIP NAT mappings.
The operator must add the new bridge subnet to the existing PJSIP transport's
`local_net` list so the public trunk's NAT settings do not rewrite private phone
media to a public address. Transport changes may require an Asterisk restart;
schedule this with no active calls. Check `rtp show settings` rather than assuming
the media range: Asterisk's unconfigured default is 5000–31000.

The unprivileged reconciler publishes active peers every ten seconds. The runtime
uses `wg syncconf`, preserving unchanged sessions and removing omitted peers.
Only one `/32` per peer is currently supported; imports with routed subnets fail
for explicit review. Invalid or expired snapshots remove all peers. Valid
snapshots expire after five minutes, so a lost control plane cannot keep revoked
credentials usable indefinitely while the runtime remains operational. Monitor
health and the acknowledgement/handshake timestamps; a requested change is not
proof that the server applied it.

The worker can write only desired peers and read observed status. The server's
private key and fixed network policy are in a separate operator-owned read-only
mount. The worker receives only a key-free copy of that network policy.

## Prepare private configuration

Keep all artifacts outside the public repo, with directories mode `0700` and
files mode `0600`. Prepare three directories:

```text
private-vpn/
  config/server.json
  config/network.json
  desired/
  observed/
```

`server.json` has these fields; the key below is deliberately a nonworking
placeholder. For migration, retain the actual old server private key and VPN
address. Choose an unused bridge subnet that does not overlap host routes.

```json
{
  "address": "10.77.0.1/24",
  "egress_address": "10.77.1.2",
  "pbx_address": "10.77.1.1",
  "private_key": "REPLACE_WITH_PRIVATE_SERVER_KEY",
  "listen_port": 51821,
  "sip_port": 5060,
  "rtp_start": 5000,
  "rtp_end": 31000,
  "mtu": 1380
}
```

`network.json` contains the same fields except `private_key`. The reconciler does
not get access to `server.json`. Do not manually generate a permanent
`desired/peers.json`; Django is the source of truth and refreshes its short lease.

Configure these private deployment values before using the admin/import tools:

- `WIREGUARD_SERVER_ADDRESS`: the server's VPN address/prefix.
- `WIREGUARD_SERVER_PUBLIC_KEY`: the corresponding public key.
- `WIREGUARD_ENDPOINT`: the external DNS name and UDP port clients use.
- `WIREGUARD_ENCRYPTION_KEY`: a separately generated Fernet key, backed up
  separately from the database. Do not reuse Django's secret key.
- `FRONTPORCH_VPN_DIR`: the absolute private directory above.
- `FRONTPORCH_VPN_BIND_IP`: the host's LAN address.
- `FRONTPORCH_VPN_PORT`: the host staging port, normally 51821.
- `FRONTPORCH_VPN_BRIDGE_SUBNET`, `FRONTPORCH_VPN_CONTAINER_IP`, and
  `FRONTPORCH_VPN_PBX_IP`: matching bridge values from the JSON.

The container listens on UDP 51821. The external port can remain unchanged;
the operator redirects the existing router rule to the new host port only at
cutover. New peer downloads use the public endpoint, not the container address.

## Import and stage without changing legacy clients

1. Save a private `wg showconf` export, interface address/MTU, and router mapping.
   This includes the server private key and optional peer PSKs, not the clients'
   private keys. Confirm the server public key matches a working client file.
   Preserve every peer's public key, address, PSK, and server keepalive setting.
   Observed roaming endpoints are not made permanent; clients announce their
   current endpoint with authenticated traffic.
   Check the legacy clients' DNS and allowed routes as well: the server export
   cannot reveal these settings. This phone-only replacement does not provide VPN
   DNS or general Internet/LAN forwarding. Resolve any such dependency before
   cutover instead of assuming the server export describes the entire client setup.
2. Resolve every peer to an existing family and a human-readable connection name.
   Optionally list the existing phone IDs that use it. Keep the mapping private.
   Missing/conflicting mappings reject the whole import. Supply the known client
   file when marking an imported peer as GDMS-managed; otherwise use manual mode.
3. Deploy the owner-approved application revision through the guarded main-push
   process with `WP816_VPN_ENABLED=0`. Only web startup runs schema migrations.
   Configure the private settings above and preview the import before applying it.
   The private bundle has `config` (the export text), `assignments` (the array
   below), and `client_configs` (optional known `.conf` texts).

   ```json
   [{"client_address":"10.77.0.2","family_id":123,"name":"Hallway gateway","provisioning_method":"manual","device_ids":[456]}]
   ```

   ```sh
   python manage.py import_wireguard_peers --bundle-stdin < private-import.json
   python manage.py import_wireguard_peers --bundle-stdin --apply < private-import.json
   ```

   A container invocation can pass the bundle over stdin; never put configuration
   or credentials in arguments. Import is atomic and audited. It does not change
   QNAP, router forwarding, or the new server's running state. Assigning phones
   updates generated PBX settings through the existing apply mechanism.
4. Review and install the updated **host-owned** deployment receiver and set its
   `WP816_VPN_ENABLED=1`. This flag is not accepted from CI's SSH request. On the
   next authorized main-push deployment, the receiver includes
   `compose.wireguard.yaml` and `compose.wireguard.registry.yaml`, pulls verified
   images before replacement, waits for migrations, then verifies VPN health.
   The original SHA/two-image-digest protocol and all deployment checks remain.
5. Stage the handset using a **new temporary client key/peer** on the new server
   and the LAN staging endpoint. Do not run the same server/client key pair
   against both live servers: authenticated roaming traffic from the old server
   can interfere with the test. Keep the original phone configuration for rollback.
   Deliver the test profile via the verified HTTPS/GDMS path and wait for automatic
   application; do not send a reboot unless a bounded observation establishes need.
6. Verify a fresh handshake, PBX registration, echo audio, an incoming call after
   more than five idle minutes, reboot recovery, and peer revocation. Test from an
   outside network before claiming general onboarding readiness. Then restore or
   retain the test peer deliberately and update its endpoint through provisioning.
7. At the coordinated cutover, stop the QNAP WireGuard server and redirect router
   forwarding to the new host port. Keep the public endpoint, server identity,
   VPN address, and legacy peer credentials unchanged. Verify every legacy phone,
   including an incoming call after idle time. No legacy handset reconfiguration
   should be needed when those identities/routes are preserved.

Both new services currently reuse the verified application image. An application
image replacement therefore also replaces the VPN container when opted in;
schedule releases as maintenance until the VPN image lifecycle is separated.
Contacts may need to register again after NAT state is lost. This is a pilot
rollout constraint, not a claim of uninterrupted production upgrades.

Setting the deployment flag back to zero stops managing these services in that
deployment path; it does not itself stop already-running containers. For rollback,
explicitly stop the new VPN services, restore the router rule, restart QNAP, and
restore any temporary pilot client profile. Do not run both servers against the
same client identities during rollback. Keep the database, server identity, and
peer encryption-key backups until migration is verified.

## Verification

```sh
uv run --frozen --python 3.12 python manage.py test directory.tests.test_wireguard directory.tests.test_wireguard_models
docker build --target network-tools -t frontporch-vpn-test-tools:local .
uv run --frozen --python 3.12 python deploy/test_wireguard_network.py
```

The integration test uses fresh fictional keys, an internal disposable Docker
network, fake PBX echo services, and no published host ports. It tests both a
legacy peer without a PSK and a peer with a PSK. It does not replace the physical
phone, real PBX, router, or external-network acceptance checks.

Sources: [WireGuard quick start](https://www.wireguard.com/quickstart/),
[WireGuard configuration/syncconf](https://git.zx2c4.com/wireguard-tools/about/src/man/wg.8),
[network namespaces](https://www.wireguard.com/netns/), and
[Asterisk endpoint/media settings](https://docs.asterisk.org/Latest_API/API_Documentation/Module_Configuration/res_pjsip/).
