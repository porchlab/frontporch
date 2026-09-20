"""Email-bound, single-use invitations to an existing family."""

from datetime import timedelta
import hashlib
import secrets
from smtplib import SMTPException

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.cache import never_cache

from .accounts import account_email_in_use, login_after_invitation

from .forms import GuardianInvitationForm, GuardianJoinForm
from .models import Family, GuardianInvitation, Parent
from .services import record_activity, lock_email_identity
from .views import _require_parent


def _primary(request):
    parent = _require_parent(request)
    if not parent.is_primary:
        raise PermissionDenied(
            "Only the primary guardian can manage guardian membership."
        )
    return parent


def _deliver(request, parent, name, email):
    """Called inside a transaction; failed delivery rolls the invitation back."""
    token = secrets.token_urlsafe(32)
    invitation = GuardianInvitation.objects.create(
        family=parent.family,
        invited_by=parent,
        display_name=name,
        email=email,
        token_digest=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(days=7),
    )
    path = reverse("directory:guardian_join", args=[token])
    url = (
        settings.FRONTPORCH_PUBLIC_URL.rstrip("/") + path
        if settings.FRONTPORCH_PUBLIC_URL
        else request.build_absolute_uri(path)
    )
    send_mail(
        f"Join the {parent.family.name} family on FrontPorch",
        f"{parent.display_name} invited you to join the {parent.family.name} family as a guardian.\n\n"
        f"Open this private link to accept: {url}\n\n"
        "This link expires in seven days and can only be used once. Joining lets you manage this family’s children, phones, contacts and calling permissions.\n"
        "If you were not expecting this invitation, you can ignore it.",
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
    return invitation


@login_required
@transaction.atomic
def invite(request):
    parent = _primary(request)
    form = GuardianInvitationForm(request.POST or None, family=parent.family)
    if request.method == "POST" and form.is_valid():
        Family.objects.select_for_update().get(pk=parent.family_id)
        if GuardianInvitation.objects.filter(
            family=parent.family, email=form.cleaned_data["email"], status="pending"
        ).exists():
            form.add_error(
                "email",
                "There is already an invitation for this email. Resend or cancel it in Family settings.",
            )
        else:
            try:
                with transaction.atomic():
                    invitation = _deliver(
                        request,
                        parent,
                        form.cleaned_data["display_name"],
                        form.cleaned_data["email"],
                    )
                    record_activity(
                        parent,
                        f"Invited {invitation.display_name} to join as a guardian.",
                    )
            except (SMTPException, OSError):
                form.add_error(
                    None,
                    "The invitation could not be emailed. Please ask your administrator to check email delivery, then try again.",
                )
            else:
                messages.success(
                    request,
                    "Guardian invitation emailed. Access begins only when they accept.",
                )
                return redirect("directory:settings")
    return render(
        request,
        "directory/form.html",
        {
            "form": form,
            "section": "settings",
            "title": "A little help on the front porch.",
            "submit_label": "Send invitation",
            "intro": "Invite a guardian to manage your existing family. The invitation is sent to their email, expires in seven days, and can only be accepted once.",
        },
    )


@login_required
@require_POST
@transaction.atomic
def invitation_action(request, invitation_id, action):
    parent = _primary(request)
    Family.objects.select_for_update().get(pk=parent.family_id)
    invitation = get_object_or_404(
        GuardianInvitation.objects.select_for_update(),
        pk=invitation_id,
        family=parent.family,
    )
    if invitation.status != "pending":
        messages.info(request, "This invitation is no longer pending.")
    elif action == "cancel":
        invitation.status = "cancelled"
        invitation.save(update_fields=["status", "updated_at"])
        record_activity(
            parent, f"Cancelled the guardian invitation for {invitation.display_name}."
        )
    elif action == "resend":
        try:
            with transaction.atomic():
                invitation.status = "replaced"
                invitation.save(update_fields=["status", "updated_at"])
                _deliver(request, parent, invitation.display_name, invitation.email)
                record_activity(
                    parent,
                    f"Resent the guardian invitation for {invitation.display_name}.",
                )
        except (SMTPException, OSError):
            messages.error(
                request,
                "The replacement could not be emailed. The original invitation has not been changed.",
            )
        else:
            messages.success(
                request, "A new invitation was emailed. The old link no longer works."
            )
    return redirect("directory:settings")


@login_required
@require_POST
@transaction.atomic
def remove(request, parent_id):
    primary = _primary(request)
    Family.objects.select_for_update().get(pk=primary.family_id)
    member = get_object_or_404(
        Parent.objects.select_for_update(),
        pk=parent_id,
        family=primary.family,
        is_primary=False,
    )
    if member.is_guardian:
        member.is_guardian = False
        member.directory_visible = False
        member.save(update_fields=["is_guardian", "directory_visible", "updated_at"])
        record_activity(primary, f"Removed guardian access for {member.display_name}.")
        messages.success(
            request,
            "Guardian access removed. Existing child calling approvals are preserved.",
        )
    return redirect("directory:settings")


@sensitive_post_parameters("password1", "password2")
@never_cache
@transaction.atomic
def join(request, token):
    invitation = get_object_or_404(
        GuardianInvitation, token_digest=hashlib.sha256(token.encode()).hexdigest()
    )
    Family.objects.select_for_update().get(pk=invitation.family_id)
    invitation = GuardianInvitation.objects.select_for_update().get(pk=invitation.pk)
    context = {"invitation": invitation}
    if not invitation.available:
        context["join_error"] = (
            "This invitation has expired or has already been used, cancelled, or replaced. Ask the primary guardian for a new invitation."
        )
        return render(request, "directory/guardian_join.html", context, status=410)
    if not invitation.invited_by.is_guardian or not invitation.invited_by.is_primary:
        context["join_error"] = (
            "The inviting guardian can no longer grant access. Ask the primary guardian for a new invitation."
        )
        return render(request, "directory/guardian_join.html", context, status=410)
    if request.method == "POST":
        lock_email_identity(invitation.email)
    form = GuardianJoinForm(request.POST or None)
    context["form"] = form
    context["existing_account"] = account_email_in_use(invitation.email)
    if request.method == "POST":
        user = request.user if request.user.is_authenticated else None
        existing_parent = getattr(user, "frontporch_parent", None) if user else None
        error = None
        if user and user.email.strip().lower() != invitation.email:
            error = "Sign in with the account whose email matches this invitation."
        elif existing_parent and (
            existing_parent.family_id != invitation.family_id
            or existing_parent.is_guardian
        ):
            error = "This account already belongs to a family. It cannot be moved by an invitation."
        elif not user and context["existing_account"]:
            error = (
                "This email already has an account. Log in to accept your invitation."
            )
        elif not user and form.is_valid():
            user = form.save(commit=False)
            user.email = invitation.email
        if error:
            context["join_error"] = error
        elif user:
            try:
                with transaction.atomic():
                    if not user.pk:
                        user.save()
                    if existing_parent:
                        parent = existing_parent
                        parent.is_guardian = True
                        parent.directory_visible = False
                        parent.save(
                            update_fields=[
                                "is_guardian",
                                "directory_visible",
                                "updated_at",
                            ]
                        )
                    else:
                        parent = Parent.objects.create(
                            user=user,
                            family=invitation.family,
                            display_name=invitation.display_name,
                            is_guardian=True,
                            directory_visible=False,
                        )
            except ValidationError:
                # Keep a concurrent name collision from becoming a server error.
                context["join_error"] = (
                    "This guardian name is already in use. Ask the primary guardian to send a new invitation."
                )
            else:
                invitation.status = "accepted"
                invitation.save(update_fields=["status", "updated_at"])
                record_activity(parent, f"{parent.display_name} joined as a guardian.")
                messages.success(
                    request, "Welcome. You’ve joined your existing family."
                )
                return login_after_invitation(request, user)
    return render(request, "directory/guardian_join.html", context)
