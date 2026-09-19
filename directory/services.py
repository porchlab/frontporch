from .models import ConferenceGroup


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


def shortcut_destination_allowed(shortcut):
    """Recheck the saved target; an old shortcut never grants calling access."""
    from .models import (
        _devices_may_call,
        _device_may_call_external,
        _device_may_call_parent_phone,
        _device_may_call_child_landline,
    )

    source = shortcut.source_device
    if (
        not shortcut.approved_by_id
        or shortcut.approved_by.family_id != source.owning_family.pk
    ):
        return False
    if shortcut.internal_target_device_id:
        target = shortcut.internal_target_device
        return target.is_active and _devices_may_call(source, target)
    if shortcut.external_target_extension_id:
        return _device_may_call_external(source, shortcut.external_target_extension)
    if shortcut.parent_phone_target_id:
        return _device_may_call_parent_phone(source, shortcut.parent_phone_target)
    if shortcut.child_landline_target_id:
        return _device_may_call_child_landline(source, shortcut.child_landline_target)
    if shortcut.conference_group_target_id:
        group = shortcut.conference_group_target
        return bool(
            group.is_active
            and group.calling_enabled
            and group.dial_extension
            and group.members.count() >= 2
            and source.assigned_child_id
            and group.members.filter(pk=source.assigned_child_id).exists()
        )
    return False


def shortcut_destinations(source):
    """Return only approved targets; contact labels are scoped to this family."""
    from .models import (
        Device,
        FamilyContact,
        Parent,
        ChildLandline,
        ConferenceGroup,
        _devices_may_call,
        _device_may_call_external,
        _device_may_call_parent_phone,
        _device_may_call_child_landline,
    )

    destinations = {}
    for device in Device.objects.filter(is_active=True).select_related(
        "assigned_child__family", "assigned_parent__family", "assigned_family"
    ):
        if _devices_may_call(source, device):
            destinations[f"device:{device.pk}"] = (
                "internal_target_device",
                device,
                f"{device.friendly_name} · {device.owning_family.name}",
            )
    for contact in FamilyContact.objects.filter(
        family=source.owning_family
    ).select_related("external_phone_number__dialable_extension"):
        extension = contact.dial_extension
        if extension and _device_may_call_external(source, extension):
            destinations[f"external:{extension.pk}"] = (
                "external_target_extension",
                extension,
                f"{contact.label} · External contact",
            )
    for parent in Parent.objects.filter(family=source.owning_family).exclude(phone=""):
        if _device_may_call_parent_phone(source, parent):
            destinations[f"parent:{parent.pk}"] = (
                "parent_phone_target",
                parent,
                f"{parent.display_name} · Phone",
            )
    for landline in ChildLandline.objects.filter(is_active=True).select_related(
        "child__family"
    ):
        if _device_may_call_child_landline(source, landline):
            destinations[f"landline:{landline.pk}"] = (
                "child_landline_target",
                landline,
                f"{landline.child.name} · Landline",
            )
    if source.assigned_child_id:
        for group in ConferenceGroup.objects.filter(
            members=source.assigned_child, is_active=True, calling_enabled=True
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
