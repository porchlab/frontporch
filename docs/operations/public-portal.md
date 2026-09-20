# Public Parent Portal

The optional deployment serves `https://front.porchlab.app` through Cloudflare
Tunnel. Phones stay on **WireGuard**; Django admin and server maintenance stay on
**Tailscale**. No router port forwarding is needed.

```text
Browser -> Cloudflare HTTPS -> cloudflared -> public-ingress:8080 -> portal:8000
Operator -> Tailscale -> existing web:8000 (including /admin/)
ATA gateway -> WireGuard -> Asterisk
```

## Readiness and scope

The public stack supports the manual procedure below and opt-in
[automatic production deployment](automatic-deployment.md) after owner-controlled
merges. Automatic deployment must be installed and enabled separately; it does not
create a tunnel or publish DNS. When enabled, it migrates the existing database
and recreates application services after successful checks.

Run deployment commands from the application checkout on the deployment host,
using its installed Docker/Compose binary. Hostnames for maintenance, SSH access,
NAS-specific paths, credentials, and backup locations belong in private operator
notes. The commands below assume the existing database and private application
are already running; this is an upgrade runbook, not an initial NAS installation.

## Prerequisites

- Docker Compose 2.24.0 or newer (`!reset` removes inherited host ports).
- A Cloudflare-managed domain and a remotely managed tunnel dedicated to this app.
- Cloudflare account access that can manage tunnels and the domain's DNS.
- Working DNS resolution and outbound connectivity from the connector to
  Cloudflare's tunnel endpoints on port 7844: UDP for QUIC or TCP for HTTP/2.
  See [Cloudflare's firewall requirements](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/).
- A current database backup stored off the NAS, plus a tested restore procedure.
- A strong, existing `DJANGO_SECRET_KEY` of at least 50 characters; do not rotate an
  existing deployment key casually, since it invalidates sessions and signed data.
- Deploy the current parent portal migrations using
  [the upgrade guide](../parent-ui-implementation.md) before enabling public traffic.
  If upgrading older production code, verify the migration's impact on existing
  calling permissions before rendering/reloading Asterisk.

## Private deployment configuration

Keep the existing private `.env` secrets and Tailscale bind address. Add/update:

```dotenv
FRONTPORCH_PUBLIC_HOST=front.porchlab.app
FRONTPORCH_PUBLIC_URL=https://front.porchlab.app
CLOUDFLARE_TUNNEL_TOKEN_FILE=./.local/cloudflare-tunnel-token
```

The public process forces its own hostname allowlist, trusted HTTPS origin, secure
cookies, HTTPS redirects, and canonical invitation URL. Do not add the public host
to the private `web` service's `DJANGO_ALLOWED_HOSTS`. Private HTTP access over
Tailscale retains its existing settings; use Tailscale Serve separately if HTTPS
is desired for administration.

Create a remotely managed tunnel named `frontporch` in Cloudflare under
**Networking → Tunnels**. Store just the connector token in the private file above. Do not
commit it, paste it into Compose, or pass it on the command line. Restrict the
containing directory to the deployment operator. Docker Compose file secrets
are bind mounts: the file must be readable by the image's non-root user (UID 65532),
using a suitable owner/ACL; verify readability before launch.
If choosing a different token location, keep it outside the Docker build context.

For the default token path, on a Linux host with ordinary Unix file permissions:

```sh
mkdir -p .local
chmod 700 .local
```

In a trusted local editor, create `.local/cloudflare-tunnel-token` containing
only the token copied from Cloudflare's connector setup, on one line. Do not
paste the full `docker run ... --token ...` installer command into this file or
execute that command: Compose manages the connector. Then set ownership and
permissions (use the host's equivalent administrative command if needed):

```sh
sudo chown 65532:65532 .local/cloudflare-tunnel-token
sudo chmod 400 .local/cloudflare-tunnel-token
docker run --rm --network none --user 65532:65532 \
  --mount "type=bind,src=$PWD/.local/cloudflare-tunnel-token,dst=/token,readonly" \
  python:3.12-slim-bookworm python -c \
  'from pathlib import Path; assert Path("/token").read_text().strip(), "Empty token file"; print("Token file is readable and nonempty")'
```

The probe checks readability without printing or sending the token. NAS ACLs or
Docker user remapping may require different ownership; use the probe's result
instead of assuming `chmod` alone is sufficient. Do not loosen permissions on
the enclosing private directory to fix a container error.

The pinned images are nginx and cloudflared multi-platform image digests. Review
and update these pins periodically for security fixes. No automatic image updates
occur during container execution.

## Stage and validate

Take a database backup and record the deployed revision before changing code.
Update/build the private and public application from the same reviewed revision.
Do not run migrations in both processes concurrently.

```sh
docker compose -f compose.yaml -f compose.public.yaml config --quiet
docker compose -f compose.yaml -f compose.public.yaml build web portal
docker compose -f compose.yaml -f compose.public.yaml run --rm --no-deps web python manage.py migrate
docker compose -f compose.yaml -f compose.public.yaml up -d --no-deps --wait --wait-timeout 180 web
docker compose -f compose.yaml -f compose.public.yaml up -d --no-deps portal public-ingress
docker compose -f compose.yaml -f compose.public.yaml exec portal python manage.py check --deploy
docker compose -f compose.yaml -f compose.public.yaml exec public-ingress nginx -t
```

`check --deploy` intentionally reports HSTS subdomain/preload warnings: the portal
does not claim HTTPS policy for other hosts. Review every other warning. The
public process rejects a missing/development/short secret key. Test private admin
access before proceeding. Do not run `down`, remove volumes, recreate Asterisk, or
reload its generated configuration just to expose the portal.

Before starting the connector, test the full ingress-to-Django path from inside
the ingress container. This does not publish the app or add a host port:

```sh
docker compose -f compose.yaml -f compose.public.yaml exec -T public-ingress sh -c \
  'wget -S -O /dev/null --header="Host: $FRONTPORCH_PUBLIC_HOST" --header="X-Forwarded-Proto: https" http://127.0.0.1:8080/welcome/'
```

Expect HTTP 200 and `Cache-Control` containing `private` and `no-store`. Retry
once the portal finishes collecting static files and starting Gunicorn if it is
still starting. Resolve persistent errors before enabling the connector. The
explicit headers simulate the trusted Cloudflare request at the private ingress;
they are not a reason to expose this listener directly.

## Cloudflare route and launch

Create one published application route:

| Field | Value |
| --- | --- |
| Hostname | `front.porchlab.app` |
| Service type | HTTP |
| Service URL | `public-ingress:8080` |
| HTTP Host Header override | Leave unset |

Cloudflare creates the tunnel DNS record. Do not point this hostname to the NAS's
home IP, Tailscale IP, `web:8000`, or `portal:8000`. The connector does not share
the Django/database Docker networks, but it still has outbound network access.
Network separation is not an outbound firewall or a substitute for reviewing
the tunnel destination. The private web host allowlist must exclude the public
hostname so an ordinary misroute is rejected there as well.

Require HTTPS at Cloudflare and leave visitor IP headers enabled. Do not add
"Cache Everything" or cache rules overriding the application's `private,
no-store` responses. FrontPorch login handles parent authentication; a Cloudflare
Access login is not required. Only static assets should be cacheable.

```sh
docker compose -f compose.yaml -f compose.public.yaml up -d --no-deps cloudflared
docker compose -f compose.yaml -f compose.public.yaml ps
docker compose -f compose.yaml -f compose.public.yaml logs --tail=80 cloudflared
```

Confirm the tunnel reports **Healthy** in Cloudflare and its logs show registered
tunnel connections. Healthy confirms the connector-to-Cloudflare connection;
it does not prove that the hostname, ingress, application, or login works. Perform
the external checks below before considering the rollout complete.

Keep using both Compose files for subsequent portal deployments. Asterisk's
WireGuard configuration, host networking, generated files, and running calls are
not changed by this overlay.

## Verify from outside the VPN

Use a device with Tailscale and WireGuard disconnected, or a mobile connection.
These unauthenticated probes do not create accounts or change family data:

```sh
for path in /welcome/ /accounts/login/ /children/ /admin /admin/ /admin/login/ /register/; do
  curl --silent --show-error --output /dev/null --write-out '%{http_code} %{url_effective}\n' \
    "https://front.porchlab.app$path"
done
curl --silent --show-error --head http://front.porchlab.app/welcome/
curl --silent --show-error --head https://front.porchlab.app/welcome/
```

Expected statuses in order: **200, 200, 302, 404, 404, 404, 404**. The HTTP request
must redirect to HTTPS (301 or 308); the HTTPS response must include `private`
and `no-store` in `Cache-Control`. If Cloudflare emits `CF-Cache-Status`, it must
not report `HIT` for portal HTML. Complete the account workflows in a browser:

- HTTPS `/welcome/` and `/accounts/login/` load; HTTP redirects to HTTPS.
- `/admin`, `/admin/`, `/admin/login/`, and `/register/` return 404.
- An existing parent can log in, load only their family's data, submit a CSRF-
  protected form, and log out. Session and CSRF cookies have `Secure` attributes.
- A guardian invitation uses the canonical HTTPS domain and can be accepted once.
  Actual email delivery requires the deployment's SMTP configuration.
- Repeated account-entry POSTs from one IP receive 429 after the burst allowance;
  another IP and ordinary GETs remain usable. The ingress allows 5 requests/minute
  with a burst of 5. Cloudflare WAF/rate rules may add protection against broader
  abuse without replacing these origin-side limits.
- Dynamic responses include `Cache-Control: private, no-store`; CDN responses are
  not cache hits. Invitation tokens are absent from nginx access logs.
- Private admin access over Tailscale and ATA registration/calls over WireGuard
  still work. No public ports were added to the NAS or router.

Perform rate-limit probes with disposable test input and no real password; use
the automated ingress test below for repeatable burst/IP-isolation coverage.

## Automated tests and validation record

On a development machine, use a local PostgreSQL instance whose user can create
test databases. Never point these commands at the production database. Node is
needed for the browser/Django parity checks; Docker must be running for ingress
tests. Run from the repository root:

```sh
DATABASE_URL=postgresql:///frontporch_dev uv run --frozen python manage.py test --noinput
node --test ui-prototype/tests/*.test.cjs
uv run --frozen python deploy/test_public_ingress.py
```

The Django runner creates and deletes its test database. The ingress suite uses
disposable containers, its own Docker network, a loopback-only ephemeral port,
and a mock backend; it cleans them up after the run. It does not use a Cloudflare
token, production account, or NAS connection. It validates network attachments,
admin-path denial, HTTPS redirects, forwarded-header replacement, login limits,
and invitation-token exclusion from nginx access logs.

As of the 2026-09-19 merge at `e749300`:

- 219 Django tests and 21 browser tests passed on the merged revision.
- All 7 Docker ingress tests passed during implementation.
- The built application image was tested locally with PostgreSQL, migrations,
  Gunicorn, and nginx: pages/static assets, secure CSRF cookie, anonymous-login
  redirect, and admin/registration denial passed. Private token files were absent
  from the image.
- Live Cloudflare/DNS/TLS, real SMTP delivery, NAS rollout, and post-rollout phone
  calls remain unverified. Local tests do not replace that acceptance check.

## Troubleshooting

Start with service state and recent logs; review them privately before sharing:

```sh
docker compose -f compose.yaml -f compose.public.yaml ps
docker compose -f compose.yaml -f compose.public.yaml logs --tail=100 cloudflared public-ingress portal web
```

| Symptom | Check |
| --- | --- |
| Connector exits with missing/empty token or permission denied | Check `CLOUDFLARE_TUNNEL_TOKEN_FILE`, file ownership/ACL, and the non-root readability probe. Do not print the token. |
| Tunnel inactive, connection timeouts, or Cloudflare error 1033 | Check the connector process, token, DNS resolution, and outbound UDP/TCP 7844. |
| Tunnel Healthy but HTTP 502 | Re-run the private origin probe; check `public-ingress:8080`, the portal process, and Docker networks. The tunnel service is HTTP because TLS terminates at Cloudflare. |
| HTTP 404 for the welcome/login page | Check the route's public hostname and remove an incorrect HTTP Host Header override. Admin and uninvited registration 404s are intentional; new families must use their emailed registration link. |
| HTTP 400 or repeated HTTPS redirects | Check the public hostname and forwarded protocol. Keep `frontporch.public_settings` on `portal` and route through the ingress that overwrites headers. |
| Login POST returns 403 | Check the HTTPS origin and secure CSRF cookie; clear stale cookies and use a fresh login page. Do not disable CSRF protection. |
| Login POST returns 429 | Wait for the per-IP limit to refill; check shared NAT usage before changing the limit. Restarting ingress also clears counters and should not be the routine remedy. |
| Invitation email fails | Verify the private SMTP configuration and sender. The tunnel does not provide email delivery. |

Use [Cloudflare's troubleshooting guide](https://developers.cloudflare.com/tunnel/troubleshooting/)
to separate connector failures from origin/application failures. Keep nginx at its
normal logging level: verbose errors can include private invitation URLs.

## Rollback and operations

To withdraw public access while retaining the private application and phones:

```sh
docker compose -f compose.yaml -f compose.public.yaml stop cloudflared public-ingress portal
```

Disable/remove the published hostname route if retiring it. This does not roll
back application migrations. An application rollback needs the recorded prior
revision and a compatible database or restored backup; do not switch old code
onto a newly migrated database without checking compatibility.

Back up PostgreSQL and deployment-owned configuration off the NAS. Monitor the
public login page externally and container health locally. A tunnel does not
keep the site available during a NAS power or Internet outage.

## References

- [Cloudflare Tunnel setup](https://developers.cloudflare.com/tunnel/get-started/)
- [Connector token files](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/#token-file)
- [Cloudflare forwarding headers](https://developers.cloudflare.com/fundamentals/reference/http-headers/)
- [Django deployment checks](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [nginx request limits](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html)
