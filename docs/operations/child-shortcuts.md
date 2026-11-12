# Child dial shortcuts

Each child owns one set of keys 1–9 for their FrontPorch phones. For example,
Casey's key 2 calls Alex, regardless of which of Casey's phones is used or which
handset Alex currently has. Labels, approval, and paused state belong to the
shortcut. The extension is a dialing address, not the shortcut's identity.

A shortcut to a child rings all their active FrontPorch phones, including phones
with different extensions. It excludes the calling handset. A child can assign
a key to their own other phones when at least two are active. Existing calling
permissions and both children's quiet hours still apply. Shortcuts grant no
additional access.

Replacing, deregistering, or deleting a handset preserves incoming and outgoing
child shortcuts. During a gap with no active target phones, the shortcut is shown
as unavailable and generates no call route. Enrolling a new phone for that child
restores the shortcut without copying keys. Reassigning an old handset to someone
else does not move the child's keys or redirect calls intended for that child.

The parent portal shows one **Dial shortcuts** link per child, including children
without a phone. Existing phone shortcut URLs still open that child's shared
keys. Each phonebook includes the child's shared shortcuts. Parent destinations
remain parent identities; shared household phone sources remain device-scoped.
External landline dial-in menus retain their existing model, which already targets
children independently of their FrontPorch handsets.

## Migration 0029

Use the normal guarded deployment, including its database backup, migration, and
Asterisk render/reload. Do not run old application workers against the new schema:
child-owned shortcuts now have a nullable `source_device` and a `source_child`.

The migration converts child-owned source devices to `source_child` and child
handset targets to `child_target`. It preserves row IDs, keys, labels, notes,
activation, approvers, and timestamps, even when approval is absent or a target
is currently unavailable. Runtime permission checks continue to reject stale
approvals and revoked connections. A family activity event records the migration;
its staff-only details retain the previous device references.

The database enforces exactly one source, exactly one destination, and one use of
each key per child. If two legacy phones of one child use the same key, migration
fails atomically before changing any shortcuts. It does not choose a winner, even
if the two destinations match. Check for conflicts before deployment using the
private Django shell:

```python
from django.db.models import Count
from directory.models import DialShortcut

conflicts = (
    DialShortcut.objects.filter(source_device__assigned_child__isnull=False)
    .order_by()
    .values("source_device__assigned_child_id", "digits")
    .annotate(assignments=Count("id"))
    .filter(assignments__gt=1)
)
print(conflicts.count())
```

If nonzero, review those keys with the family while the old application is still
running. Preserve their intended assignments by choosing free keys or explicitly
removing duplicates in private Admin. Pausing a conflicting assignment alone
does not free its key. Retry deployment only after the conflict is resolved;
follow the existing deployment recovery-latch procedure after a failed deploy.
Do not publish family records or private deployment logs in a PR.

After deployment, verify the child's shared shortcut page, a phonebook, generated
routes for each active source handset, and an authorized test call. A new phone
still needs its normal GDMS/SIP provisioning; this migration does not change it.

## Rollback

Restore the pre-deployment database backup together with the previous application
release using the normal operator recovery procedure, then regenerate/reload PBX
configuration. Reversing migration 0029 with child shortcuts present is refused:
there may be no original handset left, or multiple possible handsets, and choosing
one could lose or redirect keys. Empty development databases can rewind normally.
