# ADR-009: Child-Owned Landlines

## Status

Accepted. The child-to-family permission scope below is superseded by
[ADR-010](ADR-010-parent-portal-and-child-connections.md); landline transport and
spoken-menu decisions remain in effect.

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

Calls from FrontPorch devices to the landline child use the existing SIP trunk outbound path. Calls from the landline child into FrontPorch use caller ID on the shared or family-assigned public number. One permitted child rings directly without entering a menu. Multiple permitted children enter a restricted spoken selector that accepts an Admin-configured digit from `1` through `9` or an approved four-digit extension.

The restricted selector announces each active, currently authorized shortcut as “Dial [digit] for [child name],” then tells the caller that an approved four-digit extension may be entered. Asterisk generates in-band North American ringback using the committed `indications.conf` tone zone while an authorized destination rings for both direct child-landline routes and either kind of menu selection. The renderer explicitly selects the named `ring` indication because menu calls have already been answered and cannot rely on SIP signaling alone. Invalid or timed-out input replays the complete menu once. The second invalid input or timeout plays goodbye and disconnects.

The selector only accepts shortcuts and extensions that the landline child is already allowed to call under existing child-to-family relationship rules. Shortcut targets prefer all active SIP devices sharing the child's extension and use the child's active external landline only when no SIP device exists. Shortcut rows that become stale are retained for administrators but omitted from generated configuration and prompt generation. Unknown caller IDs, unknown shortcuts, unknown extensions, and unapproved targets are rejected.

FrontPorch generates each complete shortcut sentence and its menu-specific phrases with pinned Piper 1.7.0 and the female `en_US-ljspeech-medium` voice, then uses SoX with dithering disabled to produce deterministic raw 8 kHz mono μ-law audio. The model and configuration are pinned to an immutable voice repository revision and verified by SHA-256 during the image build; there is no runtime network dependency. Piper's neural noise controls use an explicit seed so uncached generation is repeatable. A child may have an optional private spoken-name pronunciation spelling that affects only generated prompts, leaving the displayed domain name unchanged. Blank overrides fall back to the normal child name. Official Asterisk Core Sounds supply retry and goodbye prompts. Prompt cache keys include the exact spoken text, voice, engine signature, generation settings, random seed, and output format. The render/apply workflow generates missing private prompts before writing config or asking Asterisk to reload.

Generated audio and spoken-name overrides are deployment-private data. Audio is stored under the custom sounds directory; neither form may be committed, placed in a public image, or treated as anonymous data. Cached files are not automatically pruned; deployments own their retention and deletion policy. Piper is GPL-3.0; the selected single-speaker American English female voice was trained from public-domain LJSpeech data. Its neural runtime and model add roughly 210 MB before image-layer compression. This offline approach accepts the larger image in exchange for natural speech, privacy, reproducibility, and no hosted TTS dependency. Parent uploads and parent-facing voice or prompt management remain outside this decision.

If the landline's phone number is also present as an external contact, the child-owned landline identity takes precedence for inbound routing. The number should not be treated as a generic external caller while an active child landline exists for it.

For the first implementation, landline setup is staff-managed through Django Admin. Parent self-service and phone-number verification are future work.

## Consequences

Advantages:

- Families with existing landlines can join FrontPorch without replacing their phone setup.
- Child-to-family approvals remain the central permission model.
- A landline child has the same kind of FrontPorch extension as a SIP-backed child.
- Asterisk configuration remains generated from Django state.

Tradeoffs:

- The compact offline eSpeak NG voice sounds more synthetic than a neural or hosted voice.
- The web image includes pinned GPL-3.0-or-later eSpeak NG and SoX command-line tooling for prompt generation, adding about 37 MB with their Debian runtime libraries.
- Child-name audio creates additional deployment-private data that operators must protect and retire deliberately.
- Calls involving a landline traverse the PSTN and may incur provider cost.
- Caller ID is used for inbound recognition, so production use should account for provider behavior and spoofing risk.
- FrontPorch cannot control calls the child places directly from the landline outside the FrontPorch dial-in flow.

## Future Considerations

Future work may add:

- parent-requested landline onboarding
- phone-number verification before activation
- parent-managed shortcut maps and child-name recordings
- clearer cost reporting for PSTN-routed calls
- richer public telephone provider support
