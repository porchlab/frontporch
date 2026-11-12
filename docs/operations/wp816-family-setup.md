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

The phone may restart while applying firmware or configuration. During registration, FrontPorch never
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

## Deregistering a phone

Open the phone under **Phone setup**, choose **Deregister phone**, and confirm
removal. The worker removes its SIP device, incoming and outgoing dial shortcuts,
download profile, and dedicated GDMS-provisioned WireGuard peer, then applies the
PBX configuration. Shared manual gateways and the person's other phones remain
available. The request is durable; keep the phone powered and connected to Wi-Fi
while the worker sends its factory-reset task.

When the phone restarts and shows its first-time setup screen, confirm that on
the progress page. FrontPorch then cancels the reset task, removes the phone from
GDMS, and verifies its absence. Only **Phone deregistered** releases the MAC and
serial number for another registration, including registration by a different
family. Registering again creates a new claim, SIP credentials, and network keys.
Wi-Fi must be configured again. The original operation journal and family
activity remain for audit; the removed phone disappears from the active list.

This handset confirmation is necessary: GDMS's API confirms task creation, but
does not document a reliable per-device reset-completion result. A cached online
flag or numeric task status cannot prove a reset. Do not confirm an ordinary
reboot. Failed or offline resets keep the claim reserved and never report the
phone ready for reuse. An unprocessed registration with no accepted or uncertain
GDMS enrollment command can be removed without resetting any hardware.

Removal runs in the existing private provisioning worker, with the same feature
gate and credentials. The public portal only records authorized intent and
physical-reset confirmation. Existing imported/pilot phones without a
`PhoneEnrollment` record still require operator removal; the portal does not
guess their GDMS identity.

Provider writes have committed intent records. On interruption, reset creation
is reconciled by its unique task name; task cancellation and device deletion are
reconciled by absence. Pending firmware tasks are cancelled before a reset, and
the reset task is cancelled before releasing the phone, preventing delayed tasks
from affecting a later owner. Uncertain writes are never blindly repeated.
**Check again** resumes reconciliation; ownership conflicts or rejected commands
require operator review of the private journal and GDMS. Do not delete operation
records or mark a claim deregistered to bypass that review.

Migration `0028` replaces unconditional MAC/serial uniqueness with uniqueness
among unreleased claims. After a phone has been registered again, reversing this
migration requires resolving the historical duplicate identities first.

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
   user (UID/GID `0:0` in the reviewed Compose services). Files are atomically
   written mode `0600`. Include the database and peer
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

Private web startup runs `prepare_phone_provisioning_storage` when enrollment is
enabled. It makes only the generated PBX configuration mount, custom sounds mount,
and `tts` directory owned by `0:0`, mode `0755`. It preserves existing files and
does not recursively change the PBX configuration tree or runtime database. The
worker uses explicit UID/GID `0:0`, drops every capability, and retains its
read-only root filesystem. The profile and receipt directories remain private
`0700`; the preparation command does not touch their ownership or mode.

Asterisk mounts generated configuration and custom sounds read-only. Its upstream
entrypoint can recursively assign `/etc/asterisk` to the Asterisk user during
startup; without that read-only boundary it can take ownership of the shared
generated directory. A UID 0 worker with no `DAC_OVERRIDE` capability cannot write
an Asterisk-owned `0755` directory. Private web previously masked this mismatch
because it can bypass those permission checks.

The worker validates create/replace/delete access before processing any enrollment.
Its health check repeats these probes and verifies receipt-directory access along
with a recent heartbeat, so a running loop cannot conceal an unwritable mount.
A failed probe stops startup or fails container health and reports the affected
storage category without printing paths, credentials, or profile contents. Keep
the mounts read-only on the Asterisk side when overriding Compose. An ordinary
protected-main deployment prepares the directories through web startup before
starting the worker; no additional host receiver installation is required.

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
cookie removal, rate limits, and private admin denial. Release-image tests
reproduce mismatched Linux directory ownership under the worker's actual dropped
capabilities, verify preparation and atomic writes, and reject read-only mounts
even with a fresh heartbeat. Real PBX tests check that startup and replacement
preserve the generated configuration writer and cannot chown its read-only mount.

Deregistration tests also cover authorization, CSRF, duplicate submissions,
credential and shortcut removal, shared gateway preservation, pending task
cancellation, lost provider replies, ownership changes, and fresh registration
after confirmed deletion. The remote factory reset and subsequent re-enrollment
still require a supervised handset acceptance test; unit tests make no claim
that a physical handset has reset.

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
