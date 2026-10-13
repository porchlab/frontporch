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
inbox. Old rows were initially retained as read-only history and did not authorize
calls. Migration 0022 archives every old row in structured `FamilyActivity`
details before removing the retired model and its table. The archive preserves
the original IDs, guardian identities, timestamps, notes, and incomplete approvals.
Staff can inspect these read-only details in the existing activity admin; parent
feeds show only a generic historical description. Current child connections and
invitations remain unchanged; old approvals are not replayed, so revoked pairs
stay revoked. Reversing the migration restores the old rows from the archive.
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
live registration. Quiet hours use the family's explicitly selected IANA time
zone, displayed in the portal. Signup and family settings expose this selection;
the browser and PBX default time zones do not determine quiet hours. Existing
families default to `America/New_York` to preserve their intended local schedules.
Times remain local recurring wall times. Generated `GotoIfTime` checks carry the
family's named zone, so daylight saving changes require no schedule conversion or
reload. Overnight intervals keep the zone on both halves and shift the morning
day group. Cross-family calls check each child's quiet hours in their own family's
zone. Changing the family zone retains saved local times, records family activity,
and regenerates phone configuration through the existing save workflow.

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

### Conference group membership

Parents can start a group with at least one of their own children and invite a
listed family or one found by its current private family code. Only a current
guardian of the recipient household can accept, selecting that household's children.
Invitations reveal current family names at review, not other households' children.
Accepting grants membership in the evolving group: member families can invite
additional families, and each family may change only its own children's membership.
The creation, invitation, and acceptance screens explain this scope explicitly.
It does not grant direct child-to-child calling permissions.

Shared group metadata is staff-managed. Parents may edit name, notes, and active
state only when all members are in their own household. Membership edits preserve
other families and may leave zero or one member; PBX generation continues to omit
groups with fewer than two members. Calling activation remains staff-only.

Group mutations serialize on the group row. Invitations are single-use, scoped to
the recipient family, cancellable by the sender household, and declineable by the
recipient household. Acceptance requires an active group, an active guardian account
in the sending household, and current sending-household membership. Leaving entirely
cancels that household's pending outgoing invitations and removes its portal access
to the group; returning requires a new invitation. Cancellation also applies to
staff membership edits, child deletion, and moving a child to another household.
Moving a child atomically removes that child's group memberships; the receiving
household must receive and accept an invitation to approve membership again.
Portal membership changes log the
actor and resulting roster in Admin history and create family-scoped activity.
Group invitations appear in the portal inbox and dashboard; they do not send email.

## Consequences

Parents approve the exact relationship described on screen. The portal records
family-scoped activity for membership, settings, phone, contact, and permission
changes. Existing Admin history remains available.

Upgrades must run migrations and regenerate/reload Asterisk configuration so the
PBX enforces the new policy. Guardian email delivery needs private SMTP settings
and an externally correct HTTPS request origin. The PBX may run in UTC; its time
zone database must support the named family zones. Keep both services restricted
to the private network. DST gaps and repeated hours follow local wall time: a
skipped minute never occurs, and a repeated blocked minute is blocked on both
occurrences.

## Future Considerations

Primary-role transfer, multiple households per account, phone self-activation,
and live phone-registration monitoring remain separate
product decisions. None is simulated by this UI.
