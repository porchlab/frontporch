# WP816 onboarding compatibility gate

## Current implementation

The first stage includes a tested GDMS UC API client, a read-only account/inventory
check, a strict WP816 XML compiler, and an isolated, expiring single-phone HTTPS
pilot. No parent enrollment page, production worker, public production profile
service, or WireGuard container is enabled by this stage. No automatic network
requests occur during Django startup.

The [family peer model and staged server](wireguard-server.md) now provide the
WireGuard side: one family can own multiple manual or GDMS-provisioned peers,
legacy imports preserve existing client identities, and both types share private
admin management and revocation. The runtime remains opt-in pending the migration
and hardware checks in that runbook.

The implementation plan requires a compatibility proof on a real WP816 before
releasing self-service enrollment. The firmware, authenticated profile delivery,
and combined VPN/SIP echo-call checks have passed on a real handset. The pilot
used an existing QNAP peer. The replacement Docker server, outside-home test,
revocation, and application timing still require verification. Unit tests do not
establish hardware compatibility.

## Live pilot results

| Check | Result |
| --- | --- |
| API authentication, organization/site lookup, and device enrollment | Verified. |
| Quick Network Configuration on firmware 1.0.1.18 | Completed after an operator-initiated factory reset; see the DNS recovery note below. |
| Existing GDMS enrollment after factory reset | Preserved; no removal or re-enrollment was needed. |
| Remote upgrade from 1.0.1.18 to 1.0.3.39 | Verified through an API-created task. The handset rebooted and reported the new version without user intervention. |
| Connectivity after upgrade | GDMS reported the phone online; refreshed inventory and live details both reported 1.0.3.39. No manual Wi-Fi reconnection was needed during the upgrade. |
| Authenticated HTTPS configuration delivery | Verified: the phone received a Basic-auth challenge, authenticated, and fetched its MAC-specific XML through a temporary HTTPS tunnel. Certificate and hostname validation were enabled in the delivered bootstrap. |
| Combined WireGuard/SIP provisioning and calls | Verified with the existing QNAP peer: the handset showed the supplied account and the operator completed the `100` echo call with two-way audio after restart. Asterisk also reported a matching registered contact. |
| Account branding | The operator confirmed a label-only GDMS update to `FrontPorch <extension>`. No explicit reboot was requested for that update. This is now the compiler default; family/person/device names are omitted from the account label. |
| Need for an explicit reboot | Inconclusive. One GDMS reboot task was sent during the initial test; the operator had already observed configuration saving. Subsequent restarts occurred without additional reboot tasks. Future tests must wait for automatic application and must not assume a reboot is necessary. |

The first upgrade request was submitted while GDMS inventory was stale: it still
reported the newer version after the handset had switched to its older firmware
bank. The handset was subsequently found disconnected from Wi-Fi. Task acceptance
and a cached version must never be treated as proof of an upgrade.

After the factory reset and successful Wi-Fi setup, the handset reported "CPE
Connection failed". CPE Diagnosis showed "DNS issue", and the operator reported
an empty DNS field. A normal reboot restored CPE connectivity. GDMS inventory and
a live-details query then both reported the actual running version, 1.0.1.18.
This recovery does not establish why DNS was missing or make factory reset a
required onboarding step. Reproduce and handle this case before claiming an
unattended onboarding flow from every factory firmware version.

Before retrying, the original task's execution window had ended. Its metadata was
preserved privately, the task was explicitly removed through GDMS, and its absence
was confirmed. One replacement upgrade was submitted only after verifying the
phone online on 1.0.1.18 and rechecking the firmware artifact checksum. The
replacement was confirmed by the handset and fresh GDMS reports. Keep such task
journals private and reconcile uncertain writes before creating replacements.

The factory reset cleared the pilot's existing VPN/SIP setup. The combined XML
restored it for the successful echo test. GDMS live details still reported the
account as `Disabled` even though its credentials were present and the call
worked. Do not treat that field alone as authoritative registration evidence;
check the PBX contact and a call.

The pilot endpoint and tunnel were stopped after the test. A separate partial
GDMS XML update disabled automatic configuration downloads and cleared only the
temporary address and HTTP credentials. No VPN/SIP settings were cleared. The
next bootstrap explicitly re-enables automatic provisioning. Keep every write's
intent and outcome in an ignored, mode-0600 journal; never print its credentials.

The target WireGuard deployment is the existing FrontPorch host in the operator's
home network, with a separate container UDP port during staging. The operator
will change router forwarding after verification. QNAP is a compatibility-test
and rollback dependency only; production enrollment must create and revoke peers
on the FrontPorch-managed server. Inventory other QNAP peers before redirecting a
shared external UDP port.

## Run the isolated profile pilot

`serve_wp816_pilot` binds only to loopback, holds one rendered profile in memory,
and writes random HTTP credentials to a new mode-0600 state file. It is not a
Django route. Use a TLS-terminating temporary tunnel whose access logs omit paths,
headers, and response bodies; never enable tunnel debug logging. Confirm the
firmware on the actual handset before providing `--verified-firmware`.

```sh
uv run --frozen --python 3.12 python manage.py serve_wp816_pilot \
  --mac <device-mac> --wireguard-config <private-conf-path> \
  --sip-config <private-json-path> --state-file .local/pilot-state.json \
  --verified-firmware 1.0.3.39
```

The SIP JSON accepts `sip_extension` (or the pilot export's `parent_extension`)
for the account label. When absent, the label is simply `FrontPorch`. The server
rejects other phone filenames, missing/wrong credentials, plain HTTP, expired
requests, and unsupported methods. It sends `no-store` and limits request rate.
It never logs request URLs or XML. The maximum lifetime is one hour; stop the
tunnel separately when finished. Do not expose the Django development server.

## Configure the operator account locally

1. Create an account at <https://www.gdms.cloud/> and complete its account security
   setup. Use GDMS Unified Communications, not GDMS Networking.
2. Enable **API Developer** in the account and obtain its client ID and secret.
3. Put the following variables in the ignored local `.env`, or supply them through
   a secret manager. Do not put values in shell command arguments, screenshots,
   tickets, commits, or chat. Protect the file with mode `0600`.

```dotenv
GDMS_REGION=us
GDMS_USERNAME=
GDMS_PASSWORD=
GDMS_CLIENT_ID=
GDMS_CLIENT_SECRET=
```

Use `eu` for an account registered in the independent EU region. The password is
the GDMS account password. The client computes the vendor-required password
digest locally; never use online hashing websites for credentials.

This command uses the normal Django settings, including the existing required
`DATABASE_URL`. It does not read or write application database records.

```sh
uv run --frozen --python 3.12 python manage.py check_gdms
uv run --frozen --python 3.12 python manage.py check_gdms --org-id <organization-id>
uv run --frozen --python 3.12 python manage.py check_gdms \
  --org-id <organization-id> --site-id <site-id> --mac <device-mac>
```

The command authenticates and reads organization, site, and optional device
inventory. It prints numeric organization/site IDs and the requested device's
model, reported firmware, and numeric status. It deliberately omits account
names, MAC/serial numbers, addresses, tokens, and raw provider responses.

A phone not yet registered in GDMS will be reported as not enrolled; this command
will not enroll it. Inventory firmware/status can be stale and does not prove
that the device is currently connected.

## API contracts implemented

`directory/gdms.py` implements the following operations with certificate-verified
HTTPS, redirects disabled, request timeouts, bounded responses, and sanitized
exceptions:

| Operation | GDMS route |
| --- | --- |
| Obtain access token | `POST /oapi/oauth/token` |
| List organizations | `GET /oapi/v1.0.0/org/list` |
| List sites | `GET /oapi/v1.0.0/site/list` |
| Exact device inventory lookup | `POST /oapi/v1.0.0/device/list` |
| Enroll one device | `POST /oapi/v1.0.0/device/add` |
| Request firmware upgrade | `POST /oapi/v1.0.0/task/add` |
| Deliver device XML | `POST /oapi/v1.0.0/device/config/xml` |

The final three are library methods for the future enrollment worker; the check
command cannot invoke them. There is no public API exposing these operations.
Device enrollment validates the per-device batch result, not just `retCode`.
Firmware requests return a task ID, not a claim that the upgrade has completed.
The firmware URL must be selected by trusted operator configuration, never from
parent-submitted input. The caller must enforce ownership before mutations.

Requests are not automatically retried. If a write times out, reconcile its
outcome before resubmitting; GDMS may have accepted it. A duplicate-device error
must not be treated as proof that the current family owns that device.

The detailed reference has inconsistencies that need live verification:

- The OAuth method table says GET, while the official API Guide uses POST. This
  client uses POST to keep account credentials out of URLs.
- The XML upload field table says URL-encoded form, while its official packet
  capture shows multipart upload. This client follows the packet capture and
  signs the file's MD5 digest as specified in the signature section.
- “Task List” repeats the task-creation schema and example. The pilot verified
  that a POST containing `orgId` returns a paginated `result` list, but numeric
  task-status meanings remain undocumented. Do not infer upgrade completion from
  a numeric task status; require fresh firmware evidence.
- Live device details use an initial request with `isFirst=1`, followed by
  `isFirst=0` polling within one minute. An empty result means no live report is
  available yet. The pilot verified this flow once CPE connectivity was restored.

## Pilot acceptance sequence

Keep the working QNAP/phone configuration available for rollback. Use a spare
phone where possible. Do not reset or upgrade an active phone as part of the
read-only check.

1. Check API credentials, select the explicit organization/site, and verify
   account permissions. Record the results privately without secrets.
2. Enroll the pilot with a neutral identifier using its label MAC/serial. Verify
   its model and identity; reject existing ownership conflicts.
3. Test the physical Wi-Fi flow: Quick Network Configuration → Via Mobile
   Browser → join hotspot → captive page → home Wi-Fi. On iPhone the page may
   appear after a delay; browsing to the hotspot router address triggered it in
   the initial test. Verify that address before publishing a fixed URL.
4. Confirm the phone connects to GDMS without manual server configuration. Check
   for a minimum firmware requirement on factory devices.
5. Select an official, stable WP816 firmware artifact, review intermediate
   upgrade requirements, and record the exact target/version and artifact
   checksum privately. Keep the phone on external power.
6. Request the update without a handset confirmation, wait for reboot, and
   verify the installed version and retained Wi-Fi configuration. Test failure
   and reconnect behavior without automatically repeating an uncertain update.
7. Deliver device-specific HTTPS provisioning settings via XML. Verify username,
   password, certificate validation, request filenames, application timing, and
   that GDMS does not later overwrite FrontPorch-managed settings.
8. Verify the combined VPN/SIP XML, persistent WireGuard connection, registration,
   two-way audio, reboot recovery, and credential revocation.

If any required step is unsupported, revise the integration explicitly. Do not
silently add operator steps to the family onboarding flow.

## Subsequent implementation after the gate

- Authenticated family enrollment page with camera barcode capture, confirmation,
  manual fallback, family authorization, and duplicate-claim protection.
- GDMS enrollment records linked to the existing family-owned peer model, hashed
  provisioning credentials, and durable onboarding jobs. Peer allocation,
  recoverable key encryption, private admin actions, and audit records are implemented.
- Firmware-first state machine with bounded retries and progress that distinguishes
  download, firmware confirmation, VPN handshake, and SIP registration.
- Isolated public HTTPS profile service with device-specific authentication,
  firmware gating, no caching, rate limits, and redacted logs.
- Deploy and validate the implemented bridge-networked WireGuard container and
  private reconciler with the real PBX/handset, including legacy migration and
  revocation recovery. The container has no Docker socket or host networking.
- External-network pilot followed by per-device QNAP migration and documented
  rollback, backups, ownership transfer, and factory-reset recovery.

## Sources

- [GDMS API Guide](https://documentation.grandstream.com/knowledge-base/gdms-api-guide/)
- [Detailed GDMS API reference](https://doc.grandstream.dev/GDMS-API/EN/)
- [Official XML upload packet example](https://doc.grandstream.dev/file/cfg.pcapng)
- [GDMS UC user guide](https://documentation.grandstream.com/knowledge-base/gdms-user-guide/)
- [WP816 user guide](https://documentation.grandstream.com/knowledge-base/wp8x6-user-guide/)
