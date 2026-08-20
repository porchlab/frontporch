# ADR-009: Child-Owned Landlines

## Status

Accepted

## Date

2026-07-06

## Context

Some families already have a household landline they want a child to keep using.

FrontPorch can still provide value for those families by letting the landline participate in the private permission model:

- FrontPorch families can call the child through a normal FrontPorch extension.
- The child can call the shared FrontPorch number from the landline and then dial a known approved extension.
- Parents continue using child-to-family approvals instead of managing every internal FrontPorch child as a separate external contact.

This is different from a grandparent, cousin, or other truly external phone number. A child-owned landline is a child endpoint whose transport happens to be the public telephone network.

## Decision

FrontPorch will model a child-owned landline as a child participant with:

- one normalized external phone number
- one normal FrontPorch extension
- a parent or guardian approval from the child's family
- active or inactive state

The landline does not receive a SIP endpoint, SIP credentials, AOR, or device registration.

Calls from FrontPorch devices to the landline child use the existing SIP trunk outbound path. Calls from the landline child into FrontPorch use caller ID on the shared or family-assigned public number. One permitted child rings directly. Multiple permitted children enter a restricted selector that accepts an Admin-configured digit from `2` through `9` or an approved four-digit extension.

The restricted selector only accepts shortcuts and extensions that the landline child is already allowed to call under existing child-to-family relationship rules. Shortcut targets prefer all active SIP devices sharing the child's extension and use the child's active external landline only when no SIP device exists. Shortcut rows that become stale are retained for administrators but omitted from generated configuration. Unknown caller IDs, unknown shortcuts, unknown extensions, and unapproved targets are rejected.

If the landline's phone number is also present as an external contact, the child-owned landline identity takes precedence for inbound routing. The number should not be treated as a generic external caller while an active child landline exists for it.

For the first implementation, landline setup is staff-managed through Django Admin. Parent self-service and phone-number verification are future work.

## Consequences

Advantages:

- Families with existing landlines can join FrontPorch without replacing their phone setup.
- Child-to-family approvals remain the central permission model.
- A landline child has the same kind of FrontPorch extension as a SIP-backed child.
- Asterisk configuration remains generated from Django state.

Tradeoffs:

- Until spoken prompts are added, the landline child must know an approved target extension or staff-configured shortcut.
- Calls involving a landline traverse the PSTN and may incur provider cost.
- Caller ID is used for inbound recognition, so production use should account for provider behavior and spoofing risk.
- FrontPorch cannot control calls the child places directly from the landline outside the FrontPorch dial-in flow.

## Future Considerations

Future work may add:

- parent-requested landline onboarding
- phone-number verification before activation
- spoken menus that enumerate configured shortcuts
- parent-managed shortcut maps and child-name recordings
- clearer cost reporting for PSTN-routed calls
- richer public telephone provider support
