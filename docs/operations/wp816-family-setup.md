# Family WP816 registration

## Family workflow

After the operator enables enrollment, sign in to the parent portal and open
**Phone setup → Register a phone**. Choose a child, a parent, or a shared household
phone. Scan the box barcodes labelled **MAC** and **S/N**, or enter those values in
the browser. Check the values and register. The camera runs locally; photos and
factory passwords are not uploaded. No server address or account password needs
to be typed on the handset.

Put the WP816 on its charger. Use **Quick Network Configuration** and the mobile
browser option to join the handset hotspot from a mobile device. Its captive
page collects home Wi-Fi details. On iPhone, this page may take a moment to open;
if needed, copy the hotspot's **Router** address from Wi-Fi settings and open it
in Safari. After **Network connection success**, reconnect the mobile device to
its normal network and return to FrontPorch. Closing the page does not stop setup.

The phone may restart while applying firmware or configuration. FrontPorch never
issues a separate reboot or factory-reset task. It waits for live firmware
verification, sends a short-lived configuration download location, then verifies
the new peer's handshake and the PBX contact. **Ready for a test call** means
those setup checks passed; it is not continuous availability monitoring. Dial
`100` for the echo test and then call an approved contact. Parent phones keep the
parent's existing extension and incoming-call preference.

This flow registers new phones. Previously imported peers and the original pilot
phone remain in private admin; the enrollment page does not claim or reprovision
them. Each new handset gets its own family-owned peer, while existing manual
peers continue to work.

## Operator enablement

The feature is off by default. Complete the protected-main review and deployment
process in [automatic deployment](automatic-deployment.md); never start a PR image
on production. The host-owned receiver change requires separate owner review and
installation. The normal SSH release contract remains one main SHA and the same
two verified image digests.

1. Keep the existing FrontPorch WireGuard deployment enabled and verify its PBX
   route. The provisioning worker needs the existing peer encryption key, public
   endpoint, server address, database, and PBX configuration/AMI access.
2. Configure `GDMS_REGION`, `GDMS_USERNAME`, `GDMS_PASSWORD`, `GDMS_CLIENT_ID`,
   `GDMS_CLIENT_SECRET`, `GDMS_ORG_ID`, and `GDMS_SITE_ID` in the private host env.
   Choose a site without overriding templates or automatic firmware policies.
   The worker checks exact MAC, serial, neutral device name, organization, site,
   and model before releasing settings. It never adopts an existing GDMS record
   that predates its durable registration intent.
3. Set `FRONTPORCH_PROVISIONING_DIR` to a private host directory. Create `profiles`
   and `receipts` subdirectories, mode `0700`, owned by the container execution
   user. Files are atomically written mode `0600`. Include the database and peer
   keyring in private backups; do not publish the short-lived profile directory.
4. After review, install the new receiver and set its host-owned
   `WP816_ENROLLMENT_ENABLED=1` alongside `WP816_VPN_ENABLED=1`. The release includes
   `compose.provisioning.yaml` and `compose.provisioning.registry.yaml`. Both new
   services reuse the verified Django image. Only private web runs migrations;
   VPN, profile service, and worker start after web readiness and PBX reload.
5. Confirm `/phone-profiles/` reaches the isolated profile service through the
   existing HTTPS ingress. Cloudflare must not cache or present an interactive
   challenge on that prefix. A synthetic missing profile must return no settings.
   Test the actual handset from a normal home network; origin health alone does
   not prove the Cloudflare-to-handset path. Keep `/admin/` private.
6. Register a new phone through a real guardian account. Verify firmware, profile
   download, recent handshake, PBX contact, and echo audio. The end user performs
   this registration; operators should not pre-create that phone's GDMS record.

The current reviewed version is **1.0.3.39**, listed as general firmware by
[Grandstream](https://www.grandstream.com/support/firmware). Before queuing an
upgrade, the worker downloads the official file and checks SHA-256 against the
hardware-tested release. A changed vendor file fails closed. The compiler and
pin must be reviewed together for later releases. A newer handset version is
flagged for compatibility review; automatic downgrade is forbidden. The URL is
vendor-owned and mutable, so the post-upgrade live version remains the final
configuration gate.

## Boundaries and recovery

The parent request stores a claim and an audit event only. It receives neither
GDMS credentials nor the WireGuard decryption key. The private worker generates
the peer and SIP account after firmware verification, renders/reloads PBX state,
and writes an expiring profile lease. GDMS gets HTTPS bootstrap credentials only.
The separate profile process has no database connection, GDMS account, peer
keyring, AMI access, PBX mount, host port, or outbound network. It can read active
leases and write receipts, but cannot issue or extend a lease. All services drop
capabilities and use read-only roots; the existing VPN privileges are unchanged.

The profile path and random HTTP Basic credentials identify one handset. Only
GET over the trusted HTTPS proxy path is accepted. The lease expires after one
hour, even if the worker stops; completion or failure removes it earlier. This
bounds access after a process failure but is not instantaneous revocation while
the worker is unavailable. The issuer encrypts its retained bootstrap credentials
with the private peer keyring, bound to the enrollment ID. Profile files contain
SIP/VPN secrets during their lease; filesystem and host backups remain private.
The public profile process's receipt only proves a response was prepared. Ready
also requires a new peer handshake and a responding PBX contact.

Every GDMS mutation gets a committed operation record before the request. An
unknown response is never blindly resent. Device registration reconciles exact
inventory identity; upgrades poll live firmware; bootstrap delivery waits for
receipt and connection evidence. See the private **Phone enrollments** admin
for the non-secret state and operation journal. A provider outage preserves the
job and retries reads. **Check again** wakes a status check, never a new write.

Failures requiring identity/ownership correction or another bootstrap attempt
need operator review in this pilot. Do not delete an operation record to retry:
first reconcile GDMS and the handset, retire any old download lease, and keep the
audit history. There is deliberately no automatic ownership transfer, key
rotation, upgrade requeue, or reboot on a timeout. Existing peer revocation stays
available through the private WireGuard admin and does not depend on GDMS.

For rollback, stop `phone-provisioner` first and remove active leases; retain the
database journal. Disable new enrollment in the portal and stop `phone-profiles`.
Use the guarded release recovery workflow for code changes. Do not roll back the
VPN service or revoke working family peers just to disable enrollment.

## Verification and known limits

Automated tests cover family isolation, guardian revocation, CSRF, duplicate
claims, immutable assignment on repeat submit, provider-write uncertainty,
firmware-first release, interrupted PBX apply, lease authentication/expiry, and
handshake-plus-contact completion. Compose and receiver tests verify secret and
network isolation and deployment ordering. Real nginx tests cover profile routing,
cookie removal, rate limits, and private admin denial.

The original hardware pilot verified GDMS firmware upgrade and authenticated
combined settings delivery. The replacement server has carried existing remote
family peers and responding SIP contacts. End-to-end registration of a new
handset, actual iPhone camera decoding, and audio through that handset remain
hardware acceptance checks. Camera permission denial has a typed-field fallback.
The fictional browser demo retains simulated installer activation; it does not
call GDMS or reproduce this deployment-specific onboarding flow.

Technical sources: [GDMS UC API reference](https://doc.grandstream.dev/GDMS-API/EN/),
[WP8x6 user guide](https://documentation.grandstream.com/knowledge-base/wp8x6-user-guide/),
[ZXing browser scanner](https://github.com/zxing-js/browser/tree/v0.2.1).
