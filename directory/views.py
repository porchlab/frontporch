import hashlib

from django.contrib import messages
from django.conf import settings
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from .services import record_activity
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.cache import never_cache

from .forms import (
    ChildBlackoutPeriodForm,
    ChildForm,
    ConferenceGroupForm,
    ExternalContactPermissionForm,
    FamilyContactForm,
    ParentRegistrationForm,
)
from .models import (
    Child,
    ChildBlackoutPeriod,
    ConferenceGroup,
    ExternalContactPermission,
    FamilyContact,
    FamilyInvitation,
)


def _current_parent(user):
    return getattr(user, "frontporch_parent", None)


def _require_parent(request):
    parent = _current_parent(request.user)
    if parent is None or not parent.is_guardian:
        raise PermissionDenied(
            "This account does not have guardian access to a family."
        )
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


def _success(request, message):
    parent = _current_parent(request.user)
    if parent:
        record_activity(parent, message)
    messages.success(request, message)


@sensitive_post_parameters("password1", "password2")
@never_cache
def register(request, token=None):
    if not settings.FRONTPORCH_ALLOW_REGISTRATION:
        raise Http404
    if request.user.is_authenticated and _current_parent(request.user):
        return redirect("directory:dashboard")
    if token is None:
        return render(request, "directory/registration_invite_required.html", status=404)
    invitation = get_object_or_404(
        FamilyInvitation.objects.select_related("family", "invited_by__user"),
        token_digest=hashlib.sha256(token.encode()).hexdigest(),
    )
    if not invitation.available:
        return render(
            request,
            "directory/registration_invite_required.html",
            {"expired": True},
            status=410,
        )
    if request.method == "POST":
        form = ParentRegistrationForm(request.POST, invitation=invitation)
        if form.is_valid():
            try:
                user = form.save()
            except ValidationError as error:
                form.add_error(None, "; ".join(error.messages))
            else:
                login(request, user)
                messages.success(request, "Your family account is ready.")
                return redirect("directory:dashboard")
    else:
        form = ParentRegistrationForm(invitation=invitation)
    response = render(
        request, "directory/register.html", {"form": form, "invitation": invitation}
    )
    # Keep tokens off external referrers while preserving the form's CSRF origin.
    response["Referrer-Policy"] = "same-origin"
    return response


@login_required
@transaction.atomic
def child_create(request):
    parent = _require_parent(request)
    if request.method == "POST":
        form = ChildForm(request.POST, family=parent.family)
        if form.is_valid():
            child = form.save()
            _success(request, f"{child.name} has a child card now.")
            return redirect("directory:dashboard")
    else:
        form = ChildForm(family=parent.family)
    return render(request, "directory/form.html", {"form": form, "title": "Add Child"})


@login_required
@transaction.atomic
def child_update(request, child_id):
    parent = _require_parent(request)
    child = get_object_or_404(Child, id=child_id, family=parent.family)
    if request.method == "POST":
        form = ChildForm(request.POST, instance=child, family=parent.family)
        if form.is_valid():
            form.save()
            _success(request, f"{child.name}'s child card was updated.")
            return redirect("directory:dashboard")
    else:
        form = ChildForm(instance=child, family=parent.family)
    return render(request, "directory/form.html", {"form": form, "title": "Edit Child"})


@login_required
@transaction.atomic
def blackout_create(request, child_id):
    parent = _require_parent(request)
    child = get_object_or_404(Child, id=child_id, family=parent.family)
    if request.method == "POST":
        form = ChildBlackoutPeriodForm(request.POST, child=child, approved_by=parent)
        if form.is_valid():
            blackout = form.save()
            _success(request, f"{blackout.label} was added for {child.name}.")
            return redirect("directory:dashboard")
    else:
        form = ChildBlackoutPeriodForm(child=child, approved_by=parent)
    return render(
        request,
        "directory/form.html",
        {"form": form, "title": f"Add quiet hours for {child.name}"},
    )


@login_required
@transaction.atomic
def blackout_update(request, blackout_id):
    parent = _require_parent(request)
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
            _success(request, f"{updated.label} was updated.")
            return redirect("directory:dashboard")
    else:
        form = ChildBlackoutPeriodForm(
            instance=blackout,
            child=blackout.child,
            approved_by=parent,
        )
    return render(
        request, "directory/form.html", {"form": form, "title": "Edit quiet hours"}
    )


@login_required
@transaction.atomic
def blackout_deactivate(request, blackout_id):
    parent = _require_parent(request)
    blackout = get_object_or_404(
        ChildBlackoutPeriod,
        id=blackout_id,
        child__family=parent.family,
    )
    if request.method == "POST":
        blackout.is_active = False
        blackout.approved_by = parent
        blackout.save()
        _success(request, f"{blackout.label} was deactivated.")
    return redirect("directory:dashboard")


@login_required
@transaction.atomic
def contact_create(request):
    parent = _require_parent(request)
    if request.method == "POST":
        form = FamilyContactForm(request.POST, family=parent.family)
        if form.is_valid():
            contact = form.save(parent.family)
            _success(request, f"{contact.label} was added to your family contacts.")
            return redirect("directory:dashboard")
    else:
        form = FamilyContactForm(family=parent.family)
    return render(
        request,
        "directory/form.html",
        {
            "form": form,
            "title": "Add an external contact",
            "section": "contacts",
            "intro": "Saving this contact approves calls both ways with every child in your family, including children you add later.",
        },
    )


@login_required
@transaction.atomic
def contact_delete(request, contact_id):
    parent = _require_parent(request)
    contact = get_object_or_404(FamilyContact, id=contact_id, family=parent.family)
    if request.method == "POST":
        label = contact.label
        ExternalContactPermission.objects.filter(
            child__family=parent.family,
            external_phone_number=contact.external_phone_number,
        ).update(approved_by=None)
        contact.delete()
        _success(request, f"{label} was removed from your family contacts.")
    return redirect("directory:dashboard")


@login_required
@transaction.atomic
def external_contact_permission_create(request):
    parent = _require_parent(request)
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
            _success(
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
    permission = get_object_or_404(
        ExternalContactPermission,
        id=permission_id,
        child__family=parent.family,
    )
    if request.method == "POST":
        permission.approved_by = None
        permission.save()
        _success(request, "That family contact permission was revoked.")
    return redirect("directory:dashboard")


@login_required
def legacy_relationship(request, **kwargs):
    _require_parent(request)
    return render(request, "directory/legacy_relationship.html", status=410)


@login_required
@transaction.atomic
def conference_group_create(request):
    parent = _require_parent(request)
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
            _success(request, f"{group.name} was created.")
            return redirect("directory:dashboard")
    else:
        form = ConferenceGroupForm(family=parent.family)
    return render(
        request, "directory/form.html", {"form": form, "title": "Add Conference Group"}
    )


@login_required
@transaction.atomic
def conference_group_update(request, group_id):
    parent = _require_parent(request)
    group = get_object_or_404(
        ConferenceGroup.objects.filter(
            id=group_id, members__family=parent.family
        ).distinct()
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
            _success(request, f"{updated.name} was updated.")
            return redirect("directory:dashboard")
    else:
        form = ConferenceGroupForm(instance=group, family=parent.family)
    return render(
        request, "directory/form.html", {"form": form, "title": "Edit Conference Group"}
    )
