# Public Parent Portal

The optional deployment serves `https://front.porchlab.app` through Cloudflare
Tunnel. Phones stay on **WireGuard**; Django admin and server maintenance stay on
**Tailscale**. No router port forwarding is needed.

```text
Browser -> Cloudflare HTTPS -> cloudflared -> public-ingress:8080 -> portal:8000
Operator -> Tailscale -> existing web:8000 (including /admin/)
ATA gateway -> WireGuard -> Asterisk
```

## Prerequisites

- Docker Compose 2.24.0 or newer (`!reset` removes inherited host ports).
- A Cloudflare-managed domain and a remotely managed tunnel dedicated to this app.
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

Create a remotely managed tunnel named `frontporch` in Cloudflare's **Networking
> Tunnels**. Store just the connector token in the private file above. Do not
commit it, paste it into Compose, or pass it on the command line. Restrict the
containing directory to the deployment operator. Docker Compose file secrets
are bind mounts: the file must be readable by the image's non-root user (UID 65532),
using a suitable owner/ACL; verify readability before launch.
If choosing a different token location, keep it outside the Docker build context.

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
docker compose -f compose.yaml -f compose.public.yaml up -d --no-deps web portal public-ingress
docker compose -f compose.yaml -f compose.public.yaml exec portal python manage.py check --deploy
docker compose -f compose.yaml -f compose.public.yaml exec public-ingress nginx -t
```

`check --deploy` intentionally reports HSTS subdomain/preload warnings: the portal
does not claim HTTPS policy for other hosts. Review every other warning. The
public process rejects a missing/development/short secret key. Test private admin
access before proceeding. Do not run `down`, remove volumes, recreate Asterisk, or
reload its generated configuration just to expose the portal.

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
docker compose -f compose.yaml -f compose.public.yaml up -d cloudflared
docker compose -f compose.yaml -f compose.public.yaml ps
```

Keep using both Compose files for subsequent portal deployments. Asterisk's
WireGuard configuration, host networking, generated files, and running calls are
not changed by this overlay.

## Verify from outside the VPN

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

Application tests: `uv run python manage.py test` with a local PostgreSQL URL.
Docker ingress tests: `uv run python deploy/test_public_ingress.py`. These use
disposable local containers and a mock backend, not real accounts or the NAS.

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
