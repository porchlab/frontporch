# ADR-007: Public Telephone Integration Through a Shared DID

## Status

Accepted

## Date

2026-06-28

## Context

FrontPorch is designed primarily as a private neighborhood communication platform.

The overwhelming majority of calls are expected to be:

- child to child
- parent to child
- family to family

over the private FrontPorch network.

However, the platform also needs limited integration with the public telephone network (PSTN) for situations such as:

- children calling parents on their mobile phones
- grandparents calling children
- trusted friends outside the FrontPorch network
- future emergency calling support

The public telephone network is considered an interoperability feature, not the primary communication mechanism.

## Decision

FrontPorch will use a single shared Direct Inward Dial (DID) number connected to the PBX through a SIP trunk.

The initial implementation will use a low-cost pay-as-you-go SIP provider, such as VoIP.ms.

The DID acts as the gateway between the public telephone network and the private FrontPorch network.

The DID is intentionally shared across all participating families. Families do not receive individual public phone numbers.

### Incoming Calls

Incoming calls are handled according to caller identity.

Unknown callers never ring children's phones.

Trusted callers are recognized by normalized phone number.

Routing rules:

- If the caller is approved for exactly one child, route directly to that child.
- If a recognized child landline is approved for multiple children, answer with a spoken menu that enumerates only active, currently authorized Admin-configured shortcuts from `2` through `9`, then offers an approved four-digit extension as an alternative.
- Replay the menu once after invalid input or timeout. After the second invalid input or timeout, play goodbye and disconnect.
- Unknown callers may be routed to parents, routed to voicemail, or rejected, depending on future policy.

External contacts are globally identified by normalized E.164 phone numbers.

Each family maintains its own private labels for those contacts.

For example, the same underlying phone number may be labeled `Sophia` by Family A and `Sophie` by Family B. These are different private names for the same external contact identity.

### Outgoing Calls

Children never dial arbitrary public phone numbers.

Instead they dial logical FrontPorch extensions.

For example, a child may dial `201`. FrontPorch then determines the parent's preferred reachability path:

- SIP application
- cellular phone
- both

If the parent uses a mobile phone, FrontPorch places the PSTN call through the SIP trunk.

Children never know the parent's real phone number. The PBX performs the mapping.

### Cost Philosophy

The expected call distribution is:

- almost all calls remain inside FrontPorch
- only occasional calls traverse the PSTN

Using a pay-as-you-go provider minimizes recurring cost.

If PSTN usage becomes significant, the architecture allows migration to alternative providers without changing the application model.

### Security

Public SIP connectivity should remain minimal.

The private FrontPorch network remains the primary transport.

Children never receive unrestricted outbound dialing.

Unknown callers never reach children directly.

Public connectivity should expose as little attack surface as practical.

Spoken child names are deployment-private data. FrontPorch generates them locally and offline into the private custom sounds directory; prompt text and audio are never sent to a hosted TTS provider. Generated audio and deployment-specific dialplan files do not belong in the public repository.

## Consequences

This decision intentionally favors simplicity for the first production version while preserving flexibility for future evolution.

Advantages:

- extremely low monthly operating cost
- simple user experience
- parents reachable without requiring additional applications
- easy onboarding for trusted external callers
- public identity separated from private extension model

Tradeoffs:

- outbound PSTN calls incur per-minute cost
- one shared public number initially
- parent mobile calls depend on the SIP provider
- public telephone integration remains an external dependency
- the compact local voice is less natural than a larger neural TTS model
- generated child-name audio must be protected and retained or deleted as private deployment data

## Future Considerations

Future versions may support:

- SIP applications for parents
- simultaneous ringing with mobile and SIP
- hosted SIP proxy
- multiple DIDs
- family-specific public numbers
- richer caller identity
- E911 support
- voicemail
- SMS notifications

These enhancements should preserve the core architectural principle: FrontPorch remains a private communication platform. The public telephone network is simply one transport into and out of that platform.
