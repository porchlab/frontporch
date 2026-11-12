from .models import ConferenceGroup


def lock_group_actor(request, parent, additional_parent_ids=()):
    """Recheck group authority under locks held through the current transaction."""
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied
    from .models import Parent

    guardians = {
        guardian.pk: guardian
        for guardian in Parent.objects.select_for_update()
        .filter(pk__in=[parent.pk, *additional_parent_ids])
        .order_by("pk")
    }
    accounts = {
        account.pk: account
        for account in get_user_model()
        .objects.select_for_update()
        .filter(pk__in=[guardian.user_id for guardian in guardians.values()])
        .order_by("pk")
    }
    for guardian in guardians.values():
        guardian.user = accounts.get(guardian.user_id)
    current = guardians.get(parent.pk)
    if (
        current is None
        or not current.is_guardian
        or current.family_id != parent.family_id
        or current.user_id != request.user.pk
        or not current.user.is_active
    ):
        raise PermissionDenied(
            "This account no longer has guardian access to this family."
        )
    return current, guardians


def group_audit_roster(group):
    return ", ".join(
        f"{name} ({family}; child #{pk})"
        for pk, name, family in group.members.order_by(
            "family__name", "name", "pk"
        ).values_list("pk", "name", "family__name")
    )


def lock_conference_groups(group_ids):
    """Serialize membership changes using the same row locks as portal acceptance."""
    return list(
        ConferenceGroup.objects.select_for_update()
        .filter(pk__in=group_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def cancel_invalid_group_invitations():
    """Cancel invitations from departed sources or superseded by a target joining."""
    from django.db.models import Exists, OuterRef, Q
    from django.utils import timezone
    from .models import GroupInvitation

    memberships = ConferenceGroup.members.through.objects.filter(
        conferencegroup_id=OuterRef("group_id"),
    )
    return (
        GroupInvitation.objects.filter(status="pending")
        .alias(
            source_is_member=Exists(
                memberships.filter(child__family_id=OuterRef("source_family_id"))
            ),
            target_is_member=Exists(
                memberships.filter(child__family_id=OuterRef("target_family_id"))
            ),
        )
        .filter(Q(source_is_member=False) | Q(target_is_member=True))
        .update(status="cancelled", updated_at=timezone.now())
    )


def explicit_conference_group_exists(children):
    child_ids = set(child.id for child in children)
    if len(child_ids) < 2:
        return False

    candidate_groups = ConferenceGroup.objects.filter(
        is_active=True,
        members__id__in=child_ids,
    ).distinct()

    for group in candidate_groups:
        member_ids = set(group.members.values_list("id", flat=True))
        if child_ids.issubset(member_ids):
            return True
    return False


def children_may_conference(children):
    participants = list(children)
    if len({child.id for child in participants}) < 2:
        return True

    return explicit_conference_group_exists(participants)


def shortcut_source(source):
    """Child-owned keys are shared by all of that child's FrontPorch phones."""
    from .models import Device

    return (
        source.assigned_child
        if isinstance(source, Device) and source.assigned_child_id
        else source
    )


def shortcut_source_family(source):
    from .models import Child

    return source.family if isinstance(source, Child) else source.owning_family


def shortcuts_for(source):
    return shortcut_source(source).dial_shortcuts.all()


def shortcut_target_allowed(source, field, target, *, require_available=True):
    """Calling permissions belong to people; availability never grants access."""
    from .models import (
        Child,
        Device,
        FamilyContact,
        ExternalContactPermission,
        _children_may_call,
        _devices_may_call,
        _device_may_call_external,
        _device_may_call_parent,
        _device_may_call_child_landline,
    )

    child = source if isinstance(source, Child) else source.assigned_child
    family = shortcut_source_family(source)
    if field == "child_target":
        permitted = family.pk == target.family_id or bool(
            child and _children_may_call(child, target)
        )
        if not permitted or not require_available:
            return permitted
        devices = target.devices.filter(is_active=True)
        if isinstance(source, Device):
            devices = devices.exclude(pk=source.pk)
        elif child.pk == target.pk:
            return devices.count() > 1
        return devices.exists()
    if field == "internal_target_device":
        if target.assigned_child_id:
            return shortcut_target_allowed(
                source,
                "child_target",
                target.assigned_child,
                require_available=require_available,
            )
        if target.assigned_parent_id:
            return shortcut_target_allowed(
                source,
                "parent_target",
                target.assigned_parent,
                require_available=require_available,
            )
        permitted = (
            family.pk == target.owning_family.pk
            if isinstance(source, Child)
            else _devices_may_call(source, target)
        )
        return permitted and (target.is_active or not require_available)
    if field == "external_target_extension":
        if not isinstance(source, Child):
            return _device_may_call_external(source, target)
        return target.is_active and (
            FamilyContact.objects.filter(
                family=family, external_phone_number=target.external_phone_number
            ).exists()
            or ExternalContactPermission.objects.filter(
                child=child,
                external_phone_number=target.external_phone_number,
                approved_by__isnull=False,
            ).exists()
        )
    if field == "parent_target":
        if not isinstance(source, Child):
            return _device_may_call_parent(source, target)
        return target.family_id == family.pk and target.has_call_destination()
    if field == "child_landline_target":
        if not isinstance(source, Child):
            return _device_may_call_child_landline(source, target)
        return target.is_active and (
            family.pk == target.child.family_id
            or _children_may_call(child, target.child)
        )
    if field == "conference_group_target":
        return bool(
            target.is_active
            and target.calling_enabled
            and target.dial_extension
            and target.members.count() >= 2
            and child
            and target.members.filter(pk=child.pk).exists()
        )
    return False


def shortcut_destination_allowed(shortcut):
    """Recheck saved approval and current permissions before rendering any route."""
    if (
        not shortcut.source
        or not shortcut.approved_by_id
        or shortcut.approved_by.family_id != shortcut.source_family.pk
    ):
        return False
    for field in (
        "child_target",
        "internal_target_device",
        "external_target_extension",
        "parent_target",
        "child_landline_target",
        "conference_group_target",
    ):
        if getattr(shortcut, field + "_id"):
            return shortcut_target_allowed(
                shortcut.source, field, getattr(shortcut, field)
            )
    return False


def shortcut_targets(shortcut, target_field, target_id):
    if shortcut.internal_target_device_id:
        if target_field == "parent_target":
            return shortcut.internal_target_device.assigned_parent_id == target_id
        if target_field == "child_target":
            return shortcut.internal_target_device.assigned_child_id == target_id
    return getattr(shortcut, target_field + "_id") == target_id


def shortcut_destinations(source):
    """Return one approved destination per child, independent of handset identity."""
    from .models import (
        Child,
        Device,
        FamilyContact,
        Parent,
        ChildLandline,
        ConferenceGroup,
    )

    family = shortcut_source_family(source)
    child = source if isinstance(source, Child) else source.assigned_child
    destinations = {}
    for target in Child.objects.select_related("family").order_by(
        "family__name", "name", "pk"
    ):
        if shortcut_target_allowed(source, "child_target", target):
            destinations[f"child:{target.pk}"] = (
                "child_target",
                target,
                f"{target.name} · {target.family.name}",
            )
    for device in Device.objects.filter(
        is_active=True, assigned_child__isnull=True, assigned_parent__isnull=True
    ).select_related("assigned_family"):
        if shortcut_target_allowed(source, "internal_target_device", device):
            destinations[f"device:{device.pk}"] = (
                "internal_target_device",
                device,
                f"{device.friendly_name} · {device.owning_family.name}",
            )
    for contact in FamilyContact.objects.filter(family=family).select_related(
        "external_phone_number__dialable_extension"
    ):
        extension = contact.dial_extension
        if extension and shortcut_target_allowed(
            source, "external_target_extension", extension
        ):
            destinations[f"external:{extension.pk}"] = (
                "external_target_extension",
                extension,
                f"{contact.label} · External contact",
            )
    for parent in Parent.objects.filter(family=family):
        if shortcut_target_allowed(source, "parent_target", parent):
            destinations[f"parent:{parent.pk}"] = (
                "parent_target",
                parent,
                f"{parent.display_name} · Extension {parent.dial_extension}",
            )
    for landline in ChildLandline.objects.filter(is_active=True).select_related(
        "child__family"
    ):
        if shortcut_target_allowed(source, "child_landline_target", landline):
            destinations[f"landline:{landline.pk}"] = (
                "child_landline_target",
                landline,
                f"{landline.child.name} · Landline",
            )
    if child:
        for group in ConferenceGroup.objects.filter(
            members=child, is_active=True, calling_enabled=True
        ).exclude(dial_extension=""):
            if group.members.count() >= 2:
                destinations[f"group:{group.pk}"] = (
                    "conference_group_target",
                    group,
                    f"{group.name} · Group call",
                )
    return destinations


def record_activity(parent, description):
    from .models import FamilyActivity

    return FamilyActivity.objects.create(
        family=parent.family, actor=parent.user, description=description
    )


def lock_email_identity(email):
    """Serialize email-based account creation across registration and invitation joins."""
    import hashlib
    from django.db import connection

    key = int.from_bytes(
        hashlib.sha256(email.strip().lower().encode()).digest()[:8], "big", signed=True
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])
