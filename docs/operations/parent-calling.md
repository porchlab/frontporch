# Parent calling through one extension

Parent calls follow [ADR-007](../architecture/ADR-007-public-telephone-integration.md):
each parent has one stable FrontPorch extension. A child's shortcut is an alias
for that extension. The same calling setting controls both ways of dialing, and
the child's phonebook shows one parent entry with its extension and shortcuts.

In **Family settings → Your guardian profile**, each guardian chooses where calls
to them ring: FrontPorch phones, their saved phone number, both, or disabled.
Choosing the phone number or both requires a valid number. New profiles default
to FrontPorch phones; entering a profile number alone does not enable outbound
mobile calling. Staff can manage the same setting in Django Admin.

Only active FrontPorch devices ring. Both rings those devices and the saved phone
number simultaneously using the existing outbound trunk. Mobile voicemail can
answer before another device; there is no separate answer-confirmation step.
Internal phones receive the child's extension as caller ID. When a provider
caller ID is configured, it applies only to the mobile leg. The pre-dial handler
uses `CHANNEL(endpoint)` to identify that leg and `CONNECTEDLINE(num,i)` to set
the identity in its outgoing SIP request. Run the isolated runtime regression
with `uv run python -m deploy.test_parent_caller_id` after building the test image
as described in [the test script](../../deploy/test_parent_caller_id.py).
Disabled removes the destination and its shortcuts from generated call routes and
phonebooks. It does not disable a parent's devices as callers or remove their
number's existing recognition for incoming calls to FrontPorch.

Parent destinations remain private to their own family. A connection with a
child in another family never authorizes calls to that child's parents. Shortcut
approval, source family, and current destination availability are rechecked when
configuration is generated. Same-household parent calls retain the existing
exception to children's quiet hours. Changing the routing setting through the
portal records a family activity; staff changes use Django Admin history.

## Upgrading existing families

Migration `0021_unified_parent_calling` runs in the normal deployment migration
step, after the normal database backup. It:

1. Preserves the oldest active parent device's extension, or the oldest inactive
   device's extension if none is active. A parent without devices gets an unused
   four-digit extension. Existing valid three-digit extensions are retained.
2. Moves the parent's other devices to that extension while retaining their SIP
   credentials and activation states. Former additional extensions stop routing;
   review affected hardware speed dials and reprint phonebooks.
3. Renames mobile shortcut targets to parent targets and converts shortcuts to
   parent devices into parent targets. It preserves shortcut IDs, keys, labels,
   notes, approving guardians, and active states.
4. Selects **both** when a parent has an active FrontPorch device and an active,
   approved, same-family child mobile shortcut from an active source. Such a
   shortcut with no active FrontPorch device selects **phone number**. All other
   parents default to **FrontPorch phones**, including saved numbers with only
   paused, unapproved, or unauthorized shortcuts. Approvals apply to the unified
   parent destination after conversion, including former device shortcuts.
5. Records the conversion and ring setting in family activity, without recording
   phone numbers or credentials.

The upgrade rejects extension collisions, invalid existing parent extensions, or
an exhausted extension namespace and rolls back atomically. Resolve these issues
privately before retrying. Parent extensions share the existing allocation lock
with devices, external contacts, child landlines, and groups. After allocation,
normal forms and model saves cannot change a parent's extension; new parent
devices use their parent's number.

The normal deployment regenerates and reloads Asterisk configuration after
migrations. No manual edits to generated configuration are needed.

For an exact rollback, restore the pre-upgrade database backup with the matching
application revision. Reversing the schema migration alone cannot recover former
per-device numbers or per-shortcut transport choices. Its conservative reverse
conversion disables devices for phone-only or disabled parents and disables
shortcuts for disabled parents; staff must review service restoration.
