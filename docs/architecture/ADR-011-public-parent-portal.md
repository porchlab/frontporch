# ADR-011: Public Parent Portal and Separate Private Networks

## Status

Accepted. Supersedes ADR-003's choice of Tailscale for family gateways and its
assumption that all application access is private.

## Date

2026-09-19

## Context

The NAS runs Django, PostgreSQL, and Asterisk. Family ATA gateways already use
WireGuard to reach Asterisk. Tailscale provides operator access to Django admin
and server maintenance. Parents need browser access through `front.porchlab.app`
without installing VPN software. The domain uses Cloudflare DNS.

## Decision

Publish only the parent portal through an outbound Cloudflare Tunnel. Keep the
default `web` service bound to its existing Tailscale address. An opt-in Compose
file adds `portal`, `public-ingress`, and `cloudflared`, without host ports.

The public Django process has its own settings and URL configuration: no admin
routes, HTTPS-only secure cookies, explicit allowed host, no shared caching of
dynamic responses, and no open family registration. Existing families can log
in; email-bound guardian invitations continue to work. New families are enrolled
through the private portal by an operator.

The ingress enforces login/account-entry rate limits by Cloudflare's client IP,
overwrites forwarding headers, rejects unknown hosts, and blocks admin paths.
Only the ingress shares the connector's Docker network; Django and PostgreSQL
service names are on separate networks. This is not an outbound firewall: keep
the tunnel's destination fixed to the ingress and keep the public hostname out
of the private web service's host allowlist. The public application still needs database
and PBX configuration access to implement authorized parent actions; it is not a
separate data store or a sandbox against application compromise.

SIP/media remains on WireGuard. Tailscale remains the administration network.
Neither phone connectivity nor parent access requires home-router port forwarding.

## Consequences

Parents retain FrontPorch's normal login and family authorization rules. Cloudflare
terminates public TLS and can process portal HTTP traffic; voice traffic does not
pass through Cloudflare. The NAS and its Internet connection remain availability
dependencies. The tunnel token stays in a private secret file.

Deployments must update both Django processes from the same revision and migrate
once before starting them. Rate limits persist across nginx workers but reset on
ingress restart. They are a first layer against abuse, not protection from a
distributed credential attack. See the [runbook](../operations/public-portal.md)
for rollout, verification, and rollback.
