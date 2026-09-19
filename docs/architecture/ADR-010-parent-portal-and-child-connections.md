# ADR-010: Parent Portal and Exact Child Connections

## Status

Accepted. Implements the approved parent UI prototype and the September 19, 2026
choices for exact child pairs and installer activation of reserved phones.

## Date

2026-09-19

## Context

The prototype presents an invitation that connects selected children in both
calling directions. The former `AllowedChildFamilyRelationship` model could also
allow parent/shared phones and implicitly combine approved children in a family.
Those scopes must not be presented as equivalent.

## Decision

`ChildConnection` records a single reciprocal pair of children from different
families, with an approving guardian from each household. Accepting an invitation
creates only the Cartesian product of the sender's selected children and the
receiver's selected children, atomically. Newly added or excluded children do not
inherit these permissions. Removing a pair disables both directions. Parent and
shared devices are not cross-family destinations. Existing same-household calling
and separately approved conference groups remain available.

The migration materializes existing effective child pairs from reciprocal legacy
approvals. It also carries pending outgoing requests into the new invitation
inbox. Old rows remain as historical records; they no longer authorize calls.
Cross-family parent/shared-phone access from the old model is retired. This
supersedes the child-to-family scope in ADR-009; its landline transport and offline
spoken-menu decisions remain unchanged. All SIP, landline, shortcut, and generated
PBX authorization paths use exact child pairs.

The parent portal uses Django templates and CSRF-protected forms. A deployment is
one private network, with admission enforced by its existing private-network
boundary. Authenticated guardians may browse an opt-in directory of family names
and individually opted-in guardian names. It never lists children, email,
telephone, address, device, or discovery-code information. Families start unlisted.
A random rotatable family code permits discovery of an unlisted family, never
calling permission. This extends the earlier exact-name discovery workflow and
preserves the prohibition on public or child-facing discovery.

Parents reserve phones with an automatically allocated four-digit extension and
random credentials. New devices are inactive. Staff configure hardware, verify it,
and activate it through Admin. Parent pages never expose SIP credentials or claim
live registration. Quiet hours use the explicitly displayed deployment/PBX time
zone, not the browser time zone.

Saved external contacts approve calling for all present and future children in
the saving household, matching the current backend. Labels stay family-private.
Removal revokes that household's contact approval and its legacy individual
grants. Shortcuts only reference already permitted destinations; every generated
configuration rechecks authorization even when a saved shortcut is stale.

Each family has one primary guardian for membership management. Migration selects
the earliest existing guardian with a linked account, falling back to the earliest
guardian record; staff can review this designation in Admin. Other guardians can
manage ordinary household settings and calling permissions. Invitations use
random email-bound tokens, store only their digests, expire in seven days, and
are single-use. Resending replaces the previous invitation; failed delivery rolls
back the replacement. Existing users must authenticate with the invited email and
possess the emailed link. Joining never moves an account from another household.
Removing a guardian revokes portal access without deleting past approvals.

## Consequences

Parents approve the exact relationship described on screen. The portal records
family-scoped activity for membership, settings, phone, contact, and permission
changes. Existing Admin history remains available.

Upgrades must run migrations and regenerate/reload Asterisk configuration so the
PBX enforces the new policy. Guardian email delivery needs private SMTP settings
and an externally correct HTTPS request origin. Operators must keep the web and
PBX time zones aligned and restrict both to the private network.

## Future Considerations

Primary-role transfer, multiple households per account, phone self-activation,
per-household time zones, and live phone-registration monitoring remain separate
product decisions. None is simulated by this UI.
