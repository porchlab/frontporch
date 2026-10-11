"""Family-scoped conference membership and invitation workflows."""

from django.contrib import messages
from django.contrib.admin.models import CHANGE
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.urls import reverse

from . import forms, models
from .services import record_activity
from .views import _log_parent_conference_group_action, _require_parent


def member_group(parent, group_id):
    # Every parent membership mutation locks the group before checking access.
    group = get_object_or_404(
        models.ConferenceGroup.objects.select_for_update(), pk=group_id
    )
    if not group.members.filter(family=parent.family).exists():
        raise Http404
    return group


def invitation_available(invitation):
    sender = invitation.sent_by
    return (
        invitation.status == "pending"
        and invitation.group.is_active
        and sender.is_guardian
        and sender.family_id == invitation.source_family_id
        and sender.user_id is not None
        and sender.user.is_active
        and invitation.group.members.filter(
            family_id=invitation.source_family_id
        ).exists()
    )


def record_group_change(parent, group, description):
    """Notify current member households without disclosing private child details."""
    record_activity(parent, description)
    for family_id in (
        group.members.exclude(family=parent.family)
        .order_by("family_id")
        .values_list("family_id", flat=True)
        .distinct()
    ):
        models.FamilyActivity.objects.create(
            family_id=family_id,
            actor=parent.user,
            description=f"The {parent.family.name} family updated its membership in {group.name}.",
        )


@login_required
@transaction.atomic
def invite(request, group_id):
    parent = _require_parent(request)
    group = member_group(parent, group_id)
    if not group.is_active:
        raise Http404
    form = forms.GroupInvitationForm(
        request.POST if request.method == "POST" else None, family=parent.family
    )
    if request.method == "POST" and form.is_valid():
        target = form.cleaned_data["target_family"]
        if group.members.filter(family=target).exists():
            form.add_error(
                None,
                "This family already belongs to the group. They manage their own children’s membership.",
            )
        elif group.invitations.filter(target_family=target, status="pending").exists():
            form.add_error(
                None, "This family already has a pending invitation to this group."
            )
        else:
            models.GroupInvitation.objects.create(
                group=group,
                source_family=parent.family,
                target_family=target,
                sent_by=parent,
            )
            record_activity(
                parent, f"Invited the {target.name} family to {group.name}."
            )
            models.FamilyActivity.objects.create(
                family=target,
                actor=request.user,
                description=f"The {parent.family.name} family invited your children to {group.name}. Review it in Invitations.",
            )
            messages.success(
                request,
                "Group invitation sent. The receiving guardian chooses which children join.",
            )
            return redirect(reverse("directory:invitations") + "?tab=sent")
    return render(
        request,
        "directory/form.html",
        {
            "section": "circle",
            "form": form,
            "title": f"Invite a family to {group.name}",
            "submit_label": "Send group invitation",
            "cancel_url_name": "directory:connections",
            "intro": "Invite a listed family or use a code shared by a parent. Their guardian must accept before any of their children join. Members can call everyone in the group and invite more families.",
        },
    )


@login_required
@transaction.atomic
def review(request, invitation_id):
    parent = _require_parent(request)
    # Lock order matches membership edits and invitation creation.
    invitation = get_object_or_404(
        models.GroupInvitation, pk=invitation_id, target_family=parent.family
    )
    group = models.ConferenceGroup.objects.select_for_update().get(
        pk=invitation.group_id
    )
    invitation = models.GroupInvitation.objects.select_for_update().get(
        pk=invitation.pk
    )
    if not invitation_available(invitation):
        messages.info(request, "This group invitation is no longer available.")
        return redirect("directory:invitations")
    form = forms.GroupAcceptForm(
        request.POST if request.method == "POST" else None, family=parent.family
    )
    if request.method == "POST" and form.is_valid():
        children = form.cleaned_data["members"]
        group.members.add(*children)
        invitation.accepted_children.set(children)
        invitation.status, invitation.responded_by = "accepted", parent
        invitation.save()
        audit_description = (
            f"Joined {group.name} with {', '.join(child.name for child in children)}."
        )
        _log_parent_conference_group_action(request, group, CHANGE, audit_description)
        # Family activity is limited to 500 characters; keep the full roster in
        # the staff audit's text field and summarize the approval here.
        child_count = len(children)
        child_label = "child" if child_count == 1 else "children"
        record_group_change(
            parent, group, f"Joined {group.name} with {child_count} {child_label}."
        )
        messages.success(request, "Your selected children joined the group.")
        return redirect("directory:connections")
    families = models.Family.objects.filter(
        children__conference_groups=group
    ).distinct()
    return render(
        request,
        "directory/form.html",
        {
            "section": "invites",
            "form": form,
            "title": f"Join {group.name}",
            "submit_label": "Join group",
            "cancel_url_name": "directory:invitations",
            "intro": f"Invited by the {invitation.source_family.name} family. Current families: {', '.join(f.name for f in families)}. Your selected children may call everyone in this group. Each family controls its own children and can invite more families. This does not create direct child-to-child connections. Calling requires at least two members and installer activation.",
        },
    )


@login_required
@require_POST
@transaction.atomic
def invitation_action(request, invitation_id, action):
    parent = _require_parent(request)
    if action not in {"cancel", "decline"}:
        raise Http404
    scope = {"source_family" if action == "cancel" else "target_family": parent.family}
    invitation = get_object_or_404(models.GroupInvitation, pk=invitation_id, **scope)
    models.ConferenceGroup.objects.select_for_update().get(pk=invitation.group_id)
    invitation = models.GroupInvitation.objects.select_for_update().get(
        pk=invitation.pk
    )
    if invitation.status == "pending":
        invitation.status = "cancelled" if action == "cancel" else "declined"
        invitation.responded_by = parent
        invitation.save()
        record_activity(
            parent,
            f"{invitation.get_status_display()} an invitation to {invitation.group.name}.",
        )
    return redirect("directory:invitations")
