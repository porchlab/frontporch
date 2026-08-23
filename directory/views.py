from django.contrib import messages
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ChildFamilyRelationshipRequestForm,
    ChildBlackoutPeriodForm,
    ChildForm,
    ConferenceGroupForm,
    ExternalContactPermissionForm,
    FamilyContactForm,
    ParentRegistrationForm,
)
from .models import (
    AllowedChildFamilyRelationship,
    Child,
    ChildBlackoutPeriod,
    ConferenceGroup,
    ExternalContactPermission,
    FamilyContact,
)


def _current_parent(user):
    return getattr(user, "frontporch_parent", None)


def _require_parent(request):
    parent = _current_parent(request.user)
    if parent is None:
        messages.error(request, "This account is not connected to a FrontPorch family.")
        return None
    return parent


def _log_parent_conference_group_action(request, group, action_flag, message):
    LogEntry.objects.create(
        user_id=request.user.pk,
        content_type=ContentType.objects.get_for_model(ConferenceGroup),
        object_id=str(group.pk),
        object_repr=str(group),
        action_flag=action_flag,
        change_message=message,
    )


def register(request):
    if request.user.is_authenticated and _current_parent(request.user):
        return redirect("directory:dashboard")
    if request.method == "POST":
        form = ParentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Your family account is ready.")
            return redirect("directory:dashboard")
    else:
        form = ParentRegistrationForm()
    return render(request, "directory/register.html", {"form": form})


@login_required
def dashboard(request):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")

    children = (
        Child.objects.filter(family=parent.family)
        .prefetch_related("blackout_periods", "external_contact_permissions")
        .order_by("name")
    )
    context = {
        "parent": parent,
        "children": children,
        "contacts": FamilyContact.objects.filter(family=parent.family).select_related(
            "external_phone_number",
            "external_phone_number__dialable_extension",
        ),
        "contact_permissions": ExternalContactPermission.objects.filter(
            child__family=parent.family
        ).select_related("child", "external_phone_number", "approved_by"),
        "outgoing_relationships": AllowedChildFamilyRelationship.objects.filter(
            child__family=parent.family
        ).select_related(
            "child",
            "target_family",
            "approved_by_child_family_guardian",
            "approved_by_target_family_guardian",
        ),
        "incoming_relationships": AllowedChildFamilyRelationship.objects.filter(
            target_family=parent.family
        ).select_related(
            "child",
            "child__family",
            "approved_by_child_family_guardian",
            "approved_by_target_family_guardian",
        ),
        "conference_groups": ConferenceGroup.objects.filter(
            members__family=parent.family
        )
        .distinct()
        .prefetch_related("members"),
    }
    return render(request, "directory/dashboard.html", context)


@login_required
@transaction.atomic
def child_create(request):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    if request.method == "POST":
        form = ChildForm(request.POST, family=parent.family)
        if form.is_valid():
            child = form.save()
            messages.success(request, f"{child.name} has a child card now.")
            return redirect("directory:dashboard")
    else:
        form = ChildForm(family=parent.family)
    return render(request, "directory/form.html", {"form": form, "title": "Add Child"})


@login_required
@transaction.atomic
def child_update(request, child_id):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    child = get_object_or_404(Child, id=child_id, family=parent.family)
    if request.method == "POST":
        form = ChildForm(request.POST, instance=child, family=parent.family)
        if form.is_valid():
            form.save()
            messages.success(request, f"{child.name}'s child card was updated.")
            return redirect("directory:dashboard")
    else:
        form = ChildForm(instance=child, family=parent.family)
    return render(request, "directory/form.html", {"form": form, "title": "Edit Child"})


@login_required
@transaction.atomic
def blackout_create(request, child_id):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    child = get_object_or_404(Child, id=child_id, family=parent.family)
    if request.method == "POST":
        form = ChildBlackoutPeriodForm(request.POST, child=child, approved_by=parent)
        if form.is_valid():
            blackout = form.save()
            messages.success(request, f"{blackout.label} was added for {child.name}.")
            return redirect("directory:dashboard")
    else:
        form = ChildBlackoutPeriodForm(child=child, approved_by=parent)
    return render(
        request,
        "directory/form.html",
        {"form": form, "title": f"Add Blackout Period for {child.name}"},
    )


@login_required
@transaction.atomic
def blackout_update(request, blackout_id):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    blackout = get_object_or_404(
        ChildBlackoutPeriod,
        id=blackout_id,
        child__family=parent.family,
    )
    if request.method == "POST":
        form = ChildBlackoutPeriodForm(
            request.POST,
            instance=blackout,
            child=blackout.child,
            approved_by=parent,
        )
        if form.is_valid():
            updated = form.save()
            messages.success(request, f"{updated.label} was updated.")
            return redirect("directory:dashboard")
    else:
        form = ChildBlackoutPeriodForm(
            instance=blackout,
            child=blackout.child,
            approved_by=parent,
        )
    return render(request, "directory/form.html", {"form": form, "title": "Edit Blackout Period"})


@login_required
@transaction.atomic
def blackout_deactivate(request, blackout_id):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    blackout = get_object_or_404(
        ChildBlackoutPeriod,
        id=blackout_id,
        child__family=parent.family,
    )
    if request.method == "POST":
        blackout.is_active = False
        blackout.approved_by = parent
        blackout.save()
        messages.success(request, f"{blackout.label} was deactivated.")
    return redirect("directory:dashboard")


@login_required
@transaction.atomic
def contact_create(request):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    if request.method == "POST":
        form = FamilyContactForm(request.POST)
        if form.is_valid():
            contact = form.save(parent.family)
            messages.success(request, f"{contact.label} was added to your family contacts.")
            return redirect("directory:dashboard")
    else:
        form = FamilyContactForm()
    return render(request, "directory/form.html", {"form": form, "title": "Add Family Contact"})


@login_required
@transaction.atomic
def contact_delete(request, contact_id):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    contact = get_object_or_404(FamilyContact, id=contact_id, family=parent.family)
    if request.method == "POST":
        label = contact.label
        ExternalContactPermission.objects.filter(
            child__family=parent.family,
            external_phone_number=contact.external_phone_number,
        ).update(approved_by=None)
        contact.delete()
        messages.success(request, f"{label} was removed from your family contacts.")
    return redirect("directory:dashboard")


@login_required
@transaction.atomic
def external_contact_permission_create(request):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    if request.method == "POST":
        form = ExternalContactPermissionForm(request.POST, family=parent.family)
        if form.is_valid():
            permission, _ = ExternalContactPermission.objects.update_or_create(
                child=form.cleaned_data["child"],
                external_phone_number=form.cleaned_data["external_phone_number"],
                defaults={
                    "approved_by": parent,
                    "notes": form.cleaned_data["notes"],
                },
            )
            messages.success(
                request,
                f"{permission.child.name} may communicate with that family contact.",
            )
            return redirect("directory:dashboard")
    else:
        form = ExternalContactPermissionForm(family=parent.family)
    return render(
        request,
        "directory/form.html",
        {"form": form, "title": "Allow a Family Contact"},
    )


@login_required
@transaction.atomic
def external_contact_permission_revoke(request, permission_id):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    permission = get_object_or_404(
        ExternalContactPermission,
        id=permission_id,
        child__family=parent.family,
    )
    if request.method == "POST":
        permission.approved_by = None
        permission.save()
        messages.success(request, "That family contact permission was revoked.")
    return redirect("directory:dashboard")


@login_required
@transaction.atomic
def child_family_relationship_request(request):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    if request.method == "POST":
        form = ChildFamilyRelationshipRequestForm(request.POST, family=parent.family)
        if form.is_valid():
            relationship = form.save(commit=False)
            relationship.target_family = form.target_family
            relationship.approved_by_child_family_guardian = parent
            relationship.save()
            messages.success(
                request,
                f"{relationship.child.name}'s request for {relationship.target_family.name} was created.",
            )
            return redirect("directory:dashboard")
    else:
        form = ChildFamilyRelationshipRequestForm(family=parent.family)
    return render(
        request,
        "directory/form.html",
        {"form": form, "title": "Request Family Permission"},
    )


@login_required
@transaction.atomic
def child_family_relationship_approve(request, relationship_id):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    relationship = get_object_or_404(
        AllowedChildFamilyRelationship,
        id=relationship_id,
        target_family=parent.family,
    )
    if request.method == "POST":
        relationship.approved_by_target_family_guardian = parent
        relationship.save()
        messages.success(request, "That family permission was approved.")
    return redirect("directory:dashboard")


@login_required
@transaction.atomic
def child_family_relationship_revoke(request, relationship_id):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    relationship = get_object_or_404(
        AllowedChildFamilyRelationship.objects.filter(
            id=relationship_id,
        ).filter(
            child__family=parent.family
        )
        | AllowedChildFamilyRelationship.objects.filter(
            id=relationship_id,
            target_family=parent.family,
        )
    )
    if request.method == "POST":
        if relationship.child.family_id == parent.family_id:
            relationship.approved_by_child_family_guardian = None
        if relationship.target_family_id == parent.family_id:
            relationship.approved_by_target_family_guardian = None
        relationship.save()
        messages.success(request, "That family permission was revoked.")
    return redirect("directory:dashboard")


@login_required
@transaction.atomic
def conference_group_create(request):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    if request.method == "POST":
        form = ConferenceGroupForm(request.POST, family=parent.family)
        if form.is_valid():
            group = form.save(commit=False)
            group.approved_by = parent
            group.save()
            form.save_m2m()
            member_names = ", ".join(
                group.members.order_by("family__name", "name").values_list(
                    "name", flat=True
                )
            )
            _log_parent_conference_group_action(
                request,
                group,
                ADDITION,
                f"Created in parent portal with members: {member_names}",
            )
            messages.success(request, f"{group.name} was created.")
            return redirect("directory:dashboard")
    else:
        form = ConferenceGroupForm(family=parent.family)
    return render(request, "directory/form.html", {"form": form, "title": "Add Conference Group"})


@login_required
@transaction.atomic
def conference_group_update(request, group_id):
    parent = _require_parent(request)
    if parent is None:
        return redirect("logout")
    group = get_object_or_404(
        ConferenceGroup.objects.filter(id=group_id, members__family=parent.family).distinct()
    )
    if request.method == "POST":
        form = ConferenceGroupForm(request.POST, instance=group, family=parent.family)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.approved_by = parent
            updated.save()
            form.save_m2m()
            member_names = ", ".join(
                updated.members.order_by("family__name", "name").values_list(
                    "name", flat=True
                )
            )
            _log_parent_conference_group_action(
                request,
                updated,
                CHANGE,
                f"Updated in parent portal; members: {member_names}",
            )
            messages.success(request, f"{updated.name} was updated.")
            return redirect("directory:dashboard")
    else:
        form = ConferenceGroupForm(instance=group, family=parent.family)
    return render(request, "directory/form.html", {"form": form, "title": "Edit Conference Group"})
