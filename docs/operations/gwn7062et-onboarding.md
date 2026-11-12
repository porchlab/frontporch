# GWN7062ET onboarding compatibility gate

This is the diagnostic foundation for [gateway onboarding #28](https://github.com/porchlab/frontporch/issues/28),
tracked separately in [#33](https://github.com/porchlab/frontporch/issues/33).
There is no family gateway registration flow or automatic gateway provisioning
yet. Keep using the existing WP816 flow and manually managed peers.

## Confirmed support and API gaps

Grandstream's [product page](https://www.grandstream.com/products/networking-solutions/routers/product/gwn7062e-gwn7062et)
and [router manual](https://documentation.grandstream.com/knowledge-base/gwn7062et-user-manual/)
support remote management through **GDMS Networking**. The router has two FXS
ports and supports one WireGuard tunnel. The [Networking guide](https://documentation.grandstream.com/knowledge-base/gwn-management-platforms-user-guide/)
documents remote firmware management and independent FXS/SIP settings per port;
its cloud version 1.1.37.6 change history includes FXS configuration support.
These web-interface features do not establish public API coverage.

The [GWN API reference](https://doc.grandstream.dev/GWN-API/EN/) was inspected on
2026-11-11. Its 133 entries documented the following:

| Capability | Public API evidence | FrontPorch status |
| --- | --- | --- |
| Authenticate | `/oauth/token`, client credentials or restricted-network password grant | Client-credentials POST verified live. Password grant has contract tests but needs live verification. |
| Enumerate networks | `/oapi/v1.0.0/network/list` | Signed read verified live. |
| Inspect a network's devices | `/oapi/v1.0.0/ap/list` | Client and synthetic contract tests. An account without registered devices returned an empty string instead of the documented list envelope; identity stays unverified. |
| Read recommended firmware | `/oapi/v1.0.0/upgrade/version` | Read accepted with an empty result; a real gateway recommendation remains unverified. |
| Claim hardware | `/oapi/v1.0.0/ap/add`, MAC/password/network | Documented; not implemented or exercised. Password validation and ownership conflicts need a supervised pilot. |
| Upgrade firmware | `/oapi/v1.0.0/upgrade/add`, MAC list | Documented operation selects the provider recommendation and offers no explicit target-version parameter. No upgrade is implemented. |
| Configure WireGuard and FXS/SIP | No configuration endpoints found in the reviewed public reference | Obtain a supported contract from Grandstream before implementing automation. |

The reference's basic `/router/config` fields concern router/radio/Ethernet
settings; they are not an FXS configuration contract. Generic VPN alerts are not
WireGuard configuration or per-port SIP registration evidence. Missing public
documentation does not prove that no supported additional API exists.

No device was claimed, configured, upgraded, rebooted, or reset during these
checks. No model-specific API payload has been validated on hardware.

## Configure the diagnostic command

In **GDMS Networking → API Developer**, obtain its App ID and Secret Key. Keep
the working GDMS UC credentials for WP816 phones. This adapter has no UC fallback.
Store the following in the ignored local `.env` or private operator environment:

```dotenv
GWN_REGION=us
GWN_APP_ID=
GWN_SECRET_KEY=
GWN_USERNAME=
GWN_PASSWORD=
```

Use `eu` for the EU region. Leave username/password empty unless **Restrict APIs
to specific networks** is enabled, in which case configure both. Protect the
file with mode `0600`; do not put credential values in command arguments, chat,
GitHub, screenshots, or shared logs. Do not add these variables to public portal
services. This change adds no Compose credential forwarding or startup task.

Run from a normal local FrontPorch environment with its dependencies installed
and `DATABASE_URL` set (Django requires this setting). The command performs no
database queries, migrations, or device writes:

```sh
uv run --frozen python manage.py check_gwn
uv run --frozen python manage.py check_gwn --network-id <network-id>
uv run --frozen python manage.py check_gwn \
  --network-id <network-id> --mac <gateway-mac>
```

The first command prints accessible network IDs, without account/network names.
Keep live identifiers private. Supply an explicit network and the MAC from the
gateway label for a device check. It verifies accessible-network membership,
exact MAC/network/model identity, and unique results before printing reported
firmware, cloud status, and any provider recommendation. It does not print MACs,
addresses, passwords, tokens, or raw provider responses.

An empty or malformed inventory envelope is an error, not permission to claim a
gateway. A valid empty list means only that the requested device was not found
in that network. The command cannot establish whether another account owns it.
Cloud status can be stale; an online report is not VPN connectivity, SIP
registration, or successful audio. A provider recommendation is not an approved
FrontPorch firmware target and never triggers an upgrade or downgrade.

The token URL is **`https://<region-host>/oauth/token`**, without `/oapi`.
Live checks verified POST form authentication and signed JSON reads with the
token in the Authorization header. Do not copy the UC token path: initial probes
against `/oapi/oauth/token` returned 401, which did not establish that the supplied
credentials were invalid. Data requests use `/oapi/v1.0.0/`, `appID`, timestamp,
and the Networking signature including `secretKey`. The secret is never sent
as a query parameter. HTTPS verification stays enabled, redirects are rejected,
responses and pagination are bounded, and failures are not retried automatically.

## Remaining implementation and hardware gate

Keep #28 open until these outcomes have evidence. This foundation does not
satisfy its family enrollment, provisioning, or hardware acceptance criteria.

1. Obtain supported API contracts for WireGuard peer configuration/readback,
   independent FXS accounts and registration status, and selecting/verifying a
   reviewed firmware release. Record request/response schemas using fictional
   fixtures. Do not substitute browser-internal endpoints or WP816 XML settings.
2. Use a spare gateway behind an existing home router with a validated Ethernet
   uplink. Record its actual first-boot steps and retained Internet/DNS behavior.
   Do not assume the WP816 Wi-Fi enrollment procedure applies. Claiming it may
   apply cloud network settings; defer claim/reconfiguration until the supervised
   pilot and keep production/neighbor networks out of that test.
3. Validate exact identity, cloud network/device-group assignment, incorrect
   passwords, existing claims, offline devices, and API access restrictions.
   Persist mutation intent before submission and reconcile uncertain results
   without blind replay. Do not infer claim ownership from display names alone.
4. Verify firmware on the running gateway after upgrade/reboot before releasing
   calling credentials. Test interrupted upgrades and retained uplink access.
   An unfamiliar newer version needs review, not automatic downgrade. A task
   acceptance or cached inventory value is insufficient proof.
5. Establish one gateway-owned WireGuard peer serving its two independent FXS
   calling devices. Verify router-originated SIP/RTP routing, NAT, keepalive,
   firewall restrictions, reboot recovery, and the single-tunnel limit. Limit
   access to FrontPorch calling services and preserve the home's routes/DNS.
6. Exercise one and two enabled ports with separate SIP credentials and
   child/parent/shared-household assignments. Verify each PBX contact, a physical
   `100` echo test with two-way audio, and an approved-contact call per port.
   Test denials, revocation, multiple gateways, and existing WP816/manual peers.
7. Implement guardian authorization, encrypted claim credentials, durable
   operations, audit history, duplicate protection, and separate progress for
   configuration delivery, VPN connectivity, per-port SIP, and physical testing.
   Coordinate removal with [#26](https://github.com/porchlab/frontporch/issues/26);
   resetting a router can affect more than its calling accounts.

The proposed model boundary is a family-owned physical gateway and distinct
port assignments referencing existing `Device` records, with one shared peer.
Give gateway provisioning an explicit type instead of weakening the current
GDMS/WP816 one-physical-phone constraint. Reuse the existing family/guardian,
auditing, encrypted-key, PBX, and durable-operation patterns. No schema change
is included before the provisioning contract is established.

If required API operations are unavailable, the minimum candidate fallback is
operator-assisted cloud/local configuration of reviewed firmware, WireGuard,
and each FXS account, using the existing manual-peer/device model. That fallback
also needs hardware validation; it is not an automatic family onboarding flow.
Record the unsupported steps and agree the resulting product scope before
releasing a family-facing workflow.
