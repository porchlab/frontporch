# ADR-003: Private Networking via Tailscale

## Status

Superseded by [ADR-011](ADR-011-public-parent-portal.md). The private voice-network
boundary remains; ATA connectivity uses WireGuard and administration uses Tailscale.

## Date

2026-06-27

## Context

SIP exposed directly to the public Internet creates operational and security risks. Families should not need to configure port forwarding, firewall exceptions, dynamic DNS, or public SIP credentials to participate.

FrontPorch also has a longer-term goal: a private neighborhood network that can support more than phones.

## Decision

FrontPorch uses Tailscale as the private network backbone.

Phones, home gateways, PBX services, and administrative systems communicate over a tailnet or equivalent private networking layer. Public SIP exposure and home router port forwarding are outside the intended design.

The long-term neighborhood network may support:

- Phones
- Minecraft
- File sharing
- AI services
- Future private community applications

## Consequences

SIP services are not reachable from the public Internet by default.

Families do not need to manage inbound firewall rules or port forwarding.

Connectivity is encrypted and based on provisioned devices instead of public addresses.

Onboarding can be simpler because each home receives a private-network gateway rather than a set of manual router instructions.

The network can become shared community infrastructure, with the phone system as the first application rather than the whole purpose of the network.

FrontPorch becomes partly dependent on Tailscale behavior, availability, and account management. The design should keep the networking boundary explicit enough to support an equivalent private networking layer later.

## Future Considerations

Future ADRs should define device enrollment, gateway ownership, key rotation, subnet routing, and operator access.

If FrontPorch adopts another private networking system, that decision should supersede this ADR while preserving the no-public-SIP and no-port-forwarding constraints.
