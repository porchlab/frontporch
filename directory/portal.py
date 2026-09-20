"""Server-rendered parent workspace. Mutations remain ordinary CSRF-protected forms."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from . import forms, models
from . import phonebook as phonebook_service
from .services import (
    record_activity,
    shortcut_destination_allowed,
    shortcut_destinations,
)
from .views import _require_parent


def welcome(request):
    return render(request, "directory/welcome.html")


def _children(family):
    return (
        models.Child.objects.filter(family=family)
        .prefetch_related("devices__dial_shortcuts", "blackout_periods", "landlines")
        .order_by("name")
    )


def _context(parent, section):
    children = list(_children(parent.family))
    contact_count = models.FamilyContact.objects.filter(family=parent.family).count()
    for child in children:
        child.contact_count = contact_count
        child.connection_count = models.ChildConnection.objects.filter(
            Q(child_a=child) | Q(child_b=child), is_active=True
        ).count()
    return {
        "parent": parent,
        "section": section,
        "children": children,
        "contacts": models.FamilyContact.objects.filter(
            family=parent.family
        ).select_related("external_phone_number__dialable_extension"),
        "phone_done": bool(children)
        and all(
            any(d.is_active for d in c.devices.all())
            or any(l.is_active for l in c.landlines.all())
            for c in children
        ),
        "activity": parent.family.activity.select_related("actor")[:6],
    }


def overview(request):
    if not request.user.is_authenticated:
        return redirect("directory:welcome")
    parent = _require_parent(request)
    context = _context(parent, "overview")
    context["connections"] = models.ChildConnection.objects.filter(
        Q(child_a__family=parent.family) | Q(child_b__family=parent.family),
        is_active=True,
    ).select_related("child_a__family", "child_b__family")
    context["incoming_invitations"] = (
        models.ConnectionInvitation.objects.filter(
            target_family=parent.family, status="pending"
        )
        .select_related("source_family")
        .prefetch_related("source_children")
    )
    context["circle_done"] = context["connections"].exists()
    context["setup_count"] = (
        1 + int(context["phone_done"]) + int(context["circle_done"])
    )
    return render(request, "directory/dashboard.html", context)


@login_required
def children(request):
    parent = _require_parent(request)
    return render(request, "directory/children.html", _context(parent, "children"))


@login_required
def child_detail(request, child_id):
    parent = _require_parent(request)
    child = get_object_or_404(_children(parent.family), pk=child_id)
    return render(
        request, "directory/child_detail.html", {"child": child, "section": "children"}
    )


@never_cache
@login_required
@require_safe
def phonebook(request, device_id):
    parent = _require_parent(request)
    device = get_object_or_404(
        models.Device.objects.select_related("assigned_child__family"),
        pk=device_id,
        assigned_child__family=parent.family,
    )
    return render(
        request,
        "directory/phonebook.html",
        {
            "child": device.assigned_child,
            "phone_name": device.friendly_name,
            "phone_extension": device.sip_extension,
            "phone_active": device.is_active,
            "entries": phonebook_service.device_phonebook(device),
            "color": request.GET.get("style") == "color",
            "printed_on": timezone.localdate(),
        },
    )


@never_cache
@login_required
@require_safe
def landline_phonebook(request, landline_id):
    parent = _require_parent(request)
    landline = get_object_or_404(
        models.ChildLandline.objects.select_related("child__family"),
        pk=landline_id,
        child__family=parent.family,
    )
    return render(
        request,
        "directory/phonebook.html",
        {
            "child": landline.child,
            "phone_name": "Landline",
            "phone_extension": landline.dial_extension,
            "phone_active": landline.is_active,
            "is_landline": True,
            **phonebook_service.landline_phonebook(landline),
            "color": request.GET.get("style") == "color",
            "printed_on": timezone.localdate(),
        },
    )


@login_required
def contacts(request):
    parent = _require_parent(request)
    return render(request, "directory/contacts.html", _context(parent, "contacts"))


@login_required
@transaction.atomic
def contact_edit(request, contact_id):
    parent = _require_parent(request)
    contact = get_object_or_404(
        models.FamilyContact, pk=contact_id, family=parent.family
    )
    old_number_id = contact.external_phone_number_id
    form = forms.FamilyContactForm(
        request.POST or None, family=parent.family, instance=contact
    )
    if request.method == "POST" and form.is_valid():
        updated = form.save(parent.family)
        if old_number_id != updated.external_phone_number_id:
            # Removing the old family approval must not leave legacy per-child grants behind.
            for permission in models.ExternalContactPermission.objects.filter(
                child__family=parent.family,
                external_phone_number_id=old_number_id,
                approved_by__isnull=False,
            ):
                permission.approved_by = None
                permission.save()
        record_activity(parent, f"Updated external contact {updated.label}.")
        messages.success(
            request,
            "Contact saved. Calling is approved for every child in your family.",
        )
        return redirect("directory:contacts")
    return render(
        request,
        "directory/form.html",
        {
            "form": form,
            "title": "Edit external contact",
            "section": "contacts",
            "intro": "Saving approves calls both ways for all your children, including children you add later.",
            "delete_url_name": "directory:contact_delete",
            "delete_id": contact.pk,
        },
    )


@login_required
def family_directory(request):
    parent = _require_parent(request)
    query = request.GET.get("q", "").strip()[:200]
    families = models.Family.objects.filter(directory_listed=True)
    if query:
        families = families.filter(
            Q(name__icontains=query)
            | Q(
                parents__display_name__icontains=query,
                parents__directory_visible=True,
                parents__is_guardian=True,
            )
        ).distinct()
    families = families.only("id", "name").prefetch_related(
        Prefetch(
            "parents",
            queryset=models.Parent.objects.filter(
                directory_visible=True, is_guardian=True
            ).only("id", "family_id", "display_name"),
            to_attr="listed_guardians",
        )
    )
    page = Paginator(families, 24).get_page(request.GET.get("page"))
    incoming = set(
        models.ConnectionInvitation.objects.filter(
            target_family=parent.family, status="pending"
        ).values_list("source_family_id", flat=True)
    )
    outgoing = set(
        models.ConnectionInvitation.objects.filter(
            source_family=parent.family, status="pending"
        ).values_list("target_family_id", flat=True)
    )
    pairs = models.ChildConnection.objects.filter(
        Q(child_a__family=parent.family) | Q(child_b__family=parent.family),
        is_active=True,
    ).values_list("child_a__family_id", "child_b__family_id")
    connected = {
        family_id
        for pair in pairs
        for family_id in pair
        if family_id != parent.family_id
    }
    for family in page:
        family.connection_state = (
            "Invitation received"
            if family.pk in incoming
            else "Invitation sent"
            if family.pk in outgoing
            else "Connected"
            if family.pk in connected
            else ""
        )

    return render(
        request,
        "directory/family_directory.html",
        {"section": "directory", "page": page, "query": query},
    )


@login_required
@transaction.atomic
def family_settings(request):
    parent = _require_parent(request)
    family_form = forms.FamilySettingsForm(
        request.POST if request.POST.get("form") == "family" else None,
        instance=parent.family,
    )
    profile_form = forms.GuardianProfileForm(
        request.POST if request.POST.get("form") == "profile" else None, instance=parent
    )
    if request.method == "POST":
        form = (
            family_form
            if request.POST.get("form") == "family"
            else profile_form
            if request.POST.get("form") == "profile"
            else None
        )
        if form and form.is_valid():
            form.save()
            record_activity(
                parent,
                "Updated family settings."
                if form == family_form
                else "Updated guardian profile.",
            )
            messages.success(request, "Your changes are saved.")
            return redirect("directory:settings")
    return render(
        request,
        "directory/settings.html",
        {
            "section": "settings",
            "family_form": family_form,
            "profile_form": profile_form,
            "guardians": parent.family.parents.select_related("user"),
            "family_invitations": parent.family.family_invitations.filter(
                status="pending"
            ).select_related("invited_by__user"),
            "guardian_invitations": parent.family.guardian_invitations.filter(
                status="pending"
            )
            if parent.is_primary
            else [],
        },
    )


@login_required
@require_POST
@transaction.atomic
def preference(request, preference):
    parent = _require_parent(request)
    if preference == "setup":
        parent.family.setup_dismissed = request.POST.get("dismissed") == "true"
        parent.family.save(update_fields=["setup_dismissed", "updated_at"])
        return redirect("directory:dashboard")
    if preference == "emergency":
        parent.emergency_notice_dismissed = request.POST.get("dismissed") == "true"
        parent.save(update_fields=["emergency_notice_dismissed", "updated_at"])
    elif preference == "code":
        parent.family.invite_code = models.new_family_invite_code()
        parent.family.save(update_fields=["invite_code", "updated_at"])
        record_activity(parent, "Replaced the family discovery code.")
        messages.success(
            request, "A new code is ready. Your previous code no longer works."
        )
    return redirect("directory:settings")


def _source(parent, device_id):
    return get_object_or_404(
        models.Device.objects.filter(
            Q(assigned_child__family=parent.family)
            | Q(assigned_parent__family=parent.family)
            | Q(assigned_family=parent.family)
        ).select_related(
            "assigned_child__family", "assigned_parent__family", "assigned_family"
        ),
        pk=device_id,
    )


@login_required
def shortcuts(request, device_id):
    parent = _require_parent(request)
    device = _source(parent, device_id)
    destinations = shortcut_destinations(device)
    assigned = {}
    for shortcut in device.dial_shortcuts.select_related(
        "approved_by",
        "internal_target_device",
        "external_target_extension",
        "parent_phone_target",
        "child_landline_target__child",
        "conference_group_target",
    ):
        allowed = shortcut_destination_allowed(shortcut)
        label = next(
            (
                label
                for _, (field, obj, label) in destinations.items()
                if getattr(shortcut, field + "_id") == obj.pk
            ),
            "Destination unavailable",
        )
        assigned[shortcut.digits] = {
            "shortcut": shortcut,
            "target_label": label,
            "allowed": allowed,
        }
    slots = [{"digit": str(n), **assigned.get(str(n), {})} for n in range(1, 10)]
    return render(
        request,
        "directory/shortcuts.html",
        {"section": "children", "device": device, "slots": slots},
    )


@login_required
@transaction.atomic
def shortcut_edit(request, device_id, shortcut_id=None):
    parent = _require_parent(request)
    device = _source(parent, device_id)
    shortcut = (
        get_object_or_404(models.DialShortcut, pk=shortcut_id, source_device=device)
        if shortcut_id
        else None
    )
    form = forms.ShortcutForm(
        request.POST or None, source=device, parent=parent, instance=shortcut
    )
    if (
        not shortcut
        and request.GET.get("key", "") in "123456789"
        and len(request.GET.get("key", "")) == 1
    ):
        form.initial["digits"] = request.GET["key"]
    if request.method == "POST" and form.is_valid():
        models.Device.objects.select_for_update().get(pk=device.pk)
        try:
            shortcut = form.save()
        except ValidationError as error:
            form.add_error(None, "; ".join(error.messages))
        else:
            record_activity(
                parent, f"Saved shortcut {shortcut.digits} on {device.friendly_name}."
            )
            messages.success(request, "Dial shortcut saved.")
            return redirect("directory:shortcuts", device_id=device.pk)
    return render(
        request,
        "directory/form.html",
        {
            "form": form,
            "section": "children",
            "title": f"Dial shortcut · {device.friendly_name}",
            "intro": "Choose an already approved destination. Shortcuts never add calling permission; quiet hours still apply.",
        },
    )


@login_required
@require_POST
@transaction.atomic
def shortcut_action(request, shortcut_id, action):
    parent = _require_parent(request)
    shortcut = get_object_or_404(models.DialShortcut, pk=shortcut_id)
    device = _source(parent, shortcut.source_device_id)
    if action == "remove":
        shortcut.delete()
        record_activity(
            parent, f"Removed shortcut {shortcut.digits} from {device.friendly_name}."
        )
    elif action == "pause":
        # A revoked destination must still be pausable without passing target validation.
        models.DialShortcut.objects.filter(pk=shortcut.pk).update(is_active=False)
        from .asterisk.autoreload import schedule_asterisk_configuration_apply

        schedule_asterisk_configuration_apply()
        record_activity(
            parent, f"Paused shortcut {shortcut.digits} on {device.friendly_name}."
        )
    return redirect("directory:shortcuts", device_id=device.pk)


@login_required
def connections(request):
    parent = _require_parent(request)
    connections = models.ChildConnection.objects.filter(
        Q(child_a__family=parent.family) | Q(child_b__family=parent.family),
        is_active=True,
    ).select_related("child_a__family", "child_b__family")
    groups = (
        models.ConferenceGroup.objects.filter(members__family=parent.family)
        .distinct()
        .prefetch_related("members")
    )
    return render(
        request,
        "directory/connections.html",
        {"section": "circle", "connections": connections, "conference_groups": groups},
    )


@login_required
def invitations(request):
    parent = _require_parent(request)
    tab = request.GET.get("tab", "received")
    if tab not in {"received", "sent", "history"}:
        tab = "received"
    qs = models.ConnectionInvitation.objects.filter(
        Q(source_family=parent.family) | Q(target_family=parent.family)
    )
    if tab == "history":
        qs = qs.exclude(status="pending")
    else:
        qs = qs.filter(
            status="pending",
            **{
                "target_family" if tab == "received" else "source_family": parent.family
            },
        )
    qs = qs.select_related(
        "source_family", "target_family", "sent_by"
    ).prefetch_related("source_children", "accepted_children")
    return render(
        request,
        "directory/invitations.html",
        {"section": "invites", "invitations": qs, "tab": tab},
    )


@login_required
@transaction.atomic
def phone_create(request, child_id):
    import secrets

    parent = _require_parent(request)
    child = get_object_or_404(models.Child, pk=child_id, family=parent.family)
    form = forms.PhoneReservationForm(
        request.POST or None, initial={"friendly_name": f"{child.name}’s phone"}
    )
    if request.method == "POST" and form.is_valid():
        # Model saves use the same lock, including staff-managed extensions.
        models.lock_extension_namespace()
        try:
            extension = models.ExternalNumberExtension._assign_extension()
            device = models.Device.objects.create(
                assigned_child=child,
                friendly_name=form.cleaned_data["friendly_name"],
                sip_extension=extension,
                sip_username="phone-" + secrets.token_hex(12),
                sip_secret=secrets.token_urlsafe(32),
                is_active=False,
            )
        except ValidationError as error:
            form.add_error(None, "; ".join(error.messages))
        else:
            record_activity(
                parent, f"Reserved a phone for {child.name}: {device.friendly_name}."
            )
            messages.success(
                request,
                f"Extension {extension} reserved. Your installer will configure and activate this phone.",
            )
            return redirect("directory:child_detail", child_id=child.pk)
    return render(
        request,
        "directory/form.html",
        {
            "section": "children",
            "form": form,
            "title": f"A phone for {child.name}",
            "submit_label": "Reserve phone",
            "intro": "We’ll reserve an extension automatically. Your installer configures the physical phone and activates calling.",
        },
    )


@login_required
def invite_code(request):
    parent = _require_parent(request)
    form = forms.InviteCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        family = (
            models.Family.objects.filter(invite_code=form.cleaned_data["code"])
            .exclude(pk=parent.family_id)
            .first()
        )
        if family:
            request.session["discovered_family"] = {
                "id": family.pk,
                "code": family.invite_code,
            }
            from django.urls import reverse

            return redirect(
                reverse("directory:connection_invite") + f"?family={family.pk}"
            )
        form.add_error(
            "code",
            "This code is not available. Ask the parent for their current family code.",
        )
    return render(
        request,
        "directory/form.html",
        {
            "section": "directory",
            "form": form,
            "title": "A hello by invitation.",
            "submit_label": "Find family",
            "intro": "Enter the code shared by another parent. Finding a family never grants calling permission.",
        },
    )


def _discoverable_family(request, family_id):
    qs = models.Family.objects.filter(directory_listed=True)
    discovered = request.session.get("discovered_family", {})
    if discovered.get("id") and discovered.get("code"):
        qs = models.Family.objects.filter(
            Q(directory_listed=True)
            | Q(pk=discovered["id"], invite_code=discovered["code"])
        )
    return get_object_or_404(qs, pk=family_id)


@login_required
@transaction.atomic
def connection_invite(request):
    parent = _require_parent(request)
    family_id = request.GET.get("family", "")
    if not family_id.isdecimal():
        return redirect("directory:family_directory")
    target = _discoverable_family(request, int(family_id))
    if target.pk == parent.family_id:
        return redirect("directory:family_directory")
    form = forms.ConnectionInvitationForm(request.POST or None, family=parent.family)
    if request.method == "POST" and form.is_valid():
        # Consistent lock order also prevents reverse-direction duplicate invitations.
        list(
            models.Family.objects.select_for_update()
            .filter(pk__in=[parent.family_id, target.pk])
            .order_by("pk")
        )
        existing = models.ConnectionInvitation.objects.filter(status="pending").filter(
            Q(source_family=parent.family, target_family=target)
            | Q(source_family=target, target_family=parent.family)
        )
        if existing.exists():
            form.add_error(
                None,
                "There is already a pending invitation between your families. Review it in Invitations.",
            )
        else:
            invitation = models.ConnectionInvitation.objects.create(
                source_family=parent.family,
                target_family=target,
                sent_by=parent,
                message=form.cleaned_data["message"],
            )
            invitation.source_children.set(form.cleaned_data["children"])
            record_activity(parent, f"Invited the {target.name} family to connect.")
            messages.success(
                request,
                "Invitation sent. Calling stays off until the other family accepts.",
            )
            return redirect("directory:invitations")
    return render(
        request,
        "directory/form.html",
        {
            "section": "invites",
            "form": form,
            "title": f"Say hello to the {target.name} family.",
            "submit_label": "Send invitation",
            "intro": "Select your children. The receiving parent chooses which of their children to connect with them. One acceptance enables calls both ways for those selected child pairs.",
        },
    )


@login_required
@transaction.atomic
def connection_review(request, invitation_id):
    parent = _require_parent(request)
    invitation = get_object_or_404(
        models.ConnectionInvitation.objects.select_for_update(),
        pk=invitation_id,
        target_family=parent.family,
    )
    if invitation.status != "pending":
        messages.info(request, "This invitation has already been answered.")
        return redirect("directory:invitations")
    source_children = list(
        invitation.source_children.filter(family=invitation.source_family)
    )
    form = forms.ConnectionAcceptForm(request.POST or None, family=parent.family)
    if request.method == "POST" and form.is_valid():
        if (
            not source_children
            or not invitation.sent_by.is_guardian
            or invitation.sent_by.family_id != invitation.source_family_id
        ):
            form.add_error(
                None,
                "This invitation is no longer available. Ask the other family for a new invitation.",
            )
        else:
            for source in source_children:
                for target in form.cleaned_data["children"]:
                    a, b = sorted((source, target), key=lambda c: c.pk)
                    approver_a, approver_b = (
                        (invitation.sent_by, parent)
                        if a == source
                        else (parent, invitation.sent_by)
                    )
                    models.ChildConnection.objects.update_or_create(
                        child_a=a,
                        child_b=b,
                        defaults={
                            "approved_by_a": approver_a,
                            "approved_by_b": approver_b,
                            "is_active": True,
                        },
                    )
            invitation.accepted_children.set(form.cleaned_data["children"])
            invitation.status, invitation.responded_by = "accepted", parent
            invitation.save()
            record_activity(
                parent,
                f"Accepted a connection invitation from the {invitation.source_family.name} family.",
            )
            models.FamilyActivity.objects.create(
                family=invitation.source_family,
                actor=request.user,
                description=f"The {parent.family.name} family accepted your connection invitation.",
            )
            messages.success(
                request, "The selected children can now call each other both ways."
            )
            return redirect("directory:connections")
    return render(
        request,
        "directory/form.html",
        {
            "section": "invites",
            "form": form,
            "title": f"A hello from the {invitation.source_family.name} family.",
            "submit_label": "Accept invitation",
            "intro": "Connect your selected children with "
            + ", ".join(child.name for child in source_children)
            + ". Other children and parent/shared phones are not included.",
        },
    )


@login_required
@require_POST
@transaction.atomic
def invitation_action(request, invitation_id, action):
    parent = _require_parent(request)
    scope = (
        {"source_family": parent.family}
        if action == "cancel"
        else {"target_family": parent.family}
    )
    invitation = get_object_or_404(
        models.ConnectionInvitation.objects.select_for_update(),
        pk=invitation_id,
        **scope,
    )
    if invitation.status == "pending" and action in {"cancel", "decline"}:
        invitation.status = "cancelled" if action == "cancel" else "declined"
        invitation.responded_by = parent
        invitation.save()
        record_activity(
            parent, f"{invitation.get_status_display()} a family connection invitation."
        )
    return redirect("directory:invitations")


@login_required
@require_POST
@transaction.atomic
def connection_remove(request, connection_id):
    parent = _require_parent(request)
    pair = get_object_or_404(
        models.ChildConnection.objects.select_for_update().filter(
            Q(child_a__family=parent.family) | Q(child_b__family=parent.family)
        ),
        pk=connection_id,
    )
    pair.is_active = False
    pair.save()
    description = (
        f"Removed the connection between {pair.child_a.name} and {pair.child_b.name}."
    )
    record_activity(parent, description)
    other_family = (
        pair.child_b.family
        if pair.child_a.family_id == parent.family_id
        else pair.child_a.family
    )
    models.FamilyActivity.objects.create(
        family=other_family, actor=request.user, description=description
    )
    messages.success(
        request, "Calling between these children is now off in both directions."
    )
    return redirect("directory:connections")


@login_required
@transaction.atomic
def phone_edit(request, device_id):
    parent = _require_parent(request)
    device = _source(parent, device_id)
    form = forms.PhoneReservationForm(
        request.POST or None, initial={"friendly_name": device.friendly_name}
    )
    if request.method == "POST" and form.is_valid():
        device.friendly_name = form.cleaned_data["friendly_name"]
        device.save(update_fields=["friendly_name", "updated_at"])
        record_activity(parent, f"Renamed phone to {device.friendly_name}.")
        messages.success(request, "Phone name updated.")
        return redirect("directory:children")
    return render(
        request,
        "directory/form.html",
        {
            "section": "children",
            "form": form,
            "title": "A familiar name for their phone.",
            "intro": "Your installer manages activation and connection details.",
        },
    )
