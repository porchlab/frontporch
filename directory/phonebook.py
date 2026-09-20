"""Printable, family-private projections of the current calling permissions.

Use the same permission checks as shortcuts and PBX generation. This module
does not render PBX configuration or load its credentials into a print context.
Quiet hours are temporary restrictions, so they do not remove printed entries.
"""

from dataclasses import dataclass, field

from django.db.models import Q

from . import models
from .services import shortcut_destination_allowed, shortcut_destinations


@dataclass
class PhonebookEntry:
    name: str
    description: str
    extension: str
    shortcuts: list = field(default_factory=list)


def _sorted_entries(entries):
    return sorted(
        entries,
        key=lambda entry: (entry.name.casefold(), entry.description, entry.extension),
    )


def _device_entry(device):
    if device.assigned_child_id:
        name = device.assigned_child.name
    elif device.assigned_parent_id:
        name = device.assigned_parent.display_name
    else:
        name = device.friendly_name
    return PhonebookEntry(
        name, f"{device.owning_family.name} family", device.sip_extension
    )


def device_phonebook(source):
    """One entry per callable extension, with shortcuts for this device only."""
    if not source.is_active or not source.assigned_child_id:
        return []

    entries = {}
    target_entries = {}
    for target_field, target, _ in shortcut_destinations(source).values():
        if target_field == "internal_target_device":
            entry = _device_entry(target)
        elif target_field == "external_target_extension":
            # Add all external extensions below, including legacy per-child grants.
            continue
        elif target_field == "child_landline_target":
            entry = PhonebookEntry(
                target.child.name,
                f"{target.child.family.name} family · Landline",
                target.dial_extension,
            )
        elif target_field == "conference_group_target" and target.dial_extension:
            entry = PhonebookEntry(target.name, "Group call", target.dial_extension)
        else:
            # A parent's ordinary phone has no FrontPorch extension. Include it
            # only when this device has an approved, active shortcut to it.
            continue
        entry = entries.setdefault(entry.extension, entry)
        target_entries[(target_field, target.pk)] = entry

    contact_labels = dict(
        models.FamilyContact.objects.filter(family=source.owning_family).values_list(
            "external_phone_number_id", "label"
        )
    )
    extensions = models.ExternalNumberExtension.objects.filter(
        Q(external_phone_number__family_contacts__family=source.owning_family)
        | Q(
            external_phone_number__child_contact_permissions__child=source.assigned_child,
            external_phone_number__child_contact_permissions__approved_by__isnull=False,
        ),
        is_active=True,
    ).distinct()
    for extension in extensions:
        if not models._device_may_call_external(source, extension):
            continue
        entry = PhonebookEntry(
            contact_labels.get(extension.external_phone_number_id, "Approved contact"),
            "Family contact",
            extension.dial_extension,
        )
        entries[entry.extension] = entry
        target_entries[("external_target_extension", extension.pk)] = entry

    for shortcut in (
        source.dial_shortcuts.filter(is_active=True, approved_by__isnull=False)
        .select_related(
            "source_device__assigned_child__family",
            "approved_by",
            "internal_target_device__assigned_child__family",
            "internal_target_device__assigned_parent__family",
            "internal_target_device__assigned_family",
            "external_target_extension__external_phone_number",
            "parent_phone_target",
            "child_landline_target__child__family",
            "conference_group_target",
        )
        .order_by("digits", "pk")
    ):
        if not shortcut_destination_allowed(shortcut):
            continue
        if shortcut.parent_phone_target_id:
            parent = shortcut.parent_phone_target
            entry = entries.setdefault(
                ("parent", parent.pk),
                PhonebookEntry(parent.display_name, "Parent phone · shortcut only", ""),
            )
        else:
            entry = next(
                (
                    entry
                    for (target_field, target_id), entry in target_entries.items()
                    if getattr(shortcut, target_field + "_id") == target_id
                ),
                None,
            )
        if entry is not None:
            entry.shortcuts.append({"digits": shortcut.digits, "label": shortcut.label})
    return _sorted_entries(entries.values())


def landline_phonebook(source):
    """Mirror the child-only dial-in flow, including its SIP-first preference."""
    if not source.is_active:
        return {"entries": [], "dial_in_numbers": [], "direct_call": False}
    numbers = list(
        models.PublicPhoneNumber.objects.filter(
            Q(assigned_family=source.child.family) | Q(assigned_family__isnull=True),
            is_active=True,
        )
        .order_by("normalized_number")
        .values_list("normalized_number", flat=True)
    )
    entries = []
    if numbers:
        shortcuts = {
            shortcut.target_child_id: {
                "digits": shortcut.digits,
                "label": shortcut.label,
            }
            for shortcut in source.dial_shortcuts.filter(
                is_active=True,
                approved_by__family=source.child.family,
                digits__in=list("123456789"),
            )
        }
        target_child_ids = set()
        for child in (
            models.Child.objects.exclude(pk=source.child_id)
            .select_related("family")
            .prefetch_related("devices", "landlines")
        ):
            if not models._children_may_call(source.child, child):
                continue
            devices = [device for device in child.devices.all() if device.is_active]
            extensions = {device.sip_extension for device in devices} or {
                landline.dial_extension
                for landline in child.landlines.all()
                if landline.is_active
            }
            if extensions:
                target_child_ids.add(child.pk)
            for extension in sorted(extensions):
                entries.append(
                    PhonebookEntry(
                        child.name,
                        f"{child.family.name} family",
                        extension,
                        [shortcuts[child.pk]] if child.pk in shortcuts else [],
                    )
                )
        direct_call = len(target_child_ids) == 1
        if direct_call:
            # The PBX connects directly without answering into the shortcut menu.
            for entry in entries:
                entry.shortcuts = []
    else:
        direct_call = False
    return {
        "entries": _sorted_entries(entries),
        "dial_in_numbers": numbers,
        "direct_call": direct_call,
    }
