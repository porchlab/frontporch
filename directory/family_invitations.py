"""Invitations from any existing family's guardians to register a new family."""

from datetime import timedelta
import hashlib
import secrets
from smtplib import SMTPException

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import FamilyInvitationForm
from .models import Family, FamilyInvitation
from .services import record_activity
from .views import _require_parent


def _deliver(request, parent, email):
    """Called in a transaction so failed email delivery preserves existing links."""
    token = secrets.token_urlsafe(32)
    invitation = FamilyInvitation.objects.create(
        family=parent.family,
        invited_by=parent,
        email=email,
        token_digest=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(days=7),
    )
    path = reverse("directory:register_invited", args=[token])
    url = (
        settings.FRONTPORCH_PUBLIC_URL.rstrip("/") + path
        if settings.FRONTPORCH_PUBLIC_URL
        else request.build_absolute_uri(path)
    )
    delivered = send_mail(
        f"The {parent.family.name} family invited you to FrontPorch",
        f"{parent.display_name} from the {parent.family.name} family invited you "
        "to set up your own family on FrontPorch.\n\n"
        f"Open this private link to get started: {url}\n\n"
        "This invitation is for this email address, expires in seven days, and "
        "can only be used once. Each family manages its own children and phones. "
        "Calling between families requires a separate connection approved by both families.\n"
        "If you were not expecting this invitation, you can ignore it.",
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
    if delivered != 1:
        raise OSError("The email backend did not deliver the invitation.")
    return invitation


@login_required
@transaction.atomic
def invite(request):
    parent = _require_parent(request)
    if not settings.FRONTPORCH_ALLOW_REGISTRATION:
        raise Http404
    form = FamilyInvitationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        Family.objects.select_for_update().get(pk=parent.family_id)
        if FamilyInvitation.objects.filter(
            family=parent.family, email=form.cleaned_data["email"], status="pending"
        ).exists():
            form.add_error(
                "email",
                "Your family already has an invitation for this email. Resend or cancel it in Family settings.",
            )
        else:
            try:
                with transaction.atomic():
                    invitation = _deliver(request, parent, form.cleaned_data["email"])
                    record_activity(
                        parent, f"Invited {invitation.email} to register a new family."
                    )
            except (SMTPException, OSError):
                form.add_error(
                    None,
                    "The invitation could not be emailed. Please ask your administrator to check email delivery, then try again.",
                )
            else:
                messages.success(request, "Family invitation emailed.")
                return redirect("directory:settings")
    return render(
        request,
        "directory/form.html",
        {
            "form": form,
            "section": "settings",
            "title": "Invite a new family.",
            "submit_label": "Send invitation",
            "intro": "Know a family who would feel at home here? Send a parent or guardian an invitation to set up their own family. Their link expires in seven days. Calling connections still need both families’ approval.",
        },
    )


@login_required
@require_POST
@transaction.atomic
def invitation_action(request, invitation_id, action):
    parent = _require_parent(request)
    if action not in {"cancel", "resend"}:
        raise Http404
    if action == "resend" and not settings.FRONTPORCH_ALLOW_REGISTRATION:
        raise Http404
    Family.objects.select_for_update().get(pk=parent.family_id)
    invitation = get_object_or_404(
        FamilyInvitation.objects.select_for_update(),
        pk=invitation_id,
        family=parent.family,
    )
    if invitation.status != "pending":
        messages.info(request, "This invitation is no longer pending.")
    elif action == "cancel":
        invitation.status = "cancelled"
        invitation.save(update_fields=["status", "updated_at"])
        record_activity(
            parent, f"Cancelled the new family invitation for {invitation.email}."
        )
        messages.success(request, "Family invitation cancelled.")
    else:
        form = FamilyInvitationForm({"email": invitation.email})
        if not form.is_valid():
            messages.error(
                request,
                "This email already has an account. Cancel this invitation instead.",
            )
            return redirect("directory:settings")
        try:
            with transaction.atomic():
                invitation.status = "replaced"
                invitation.save(update_fields=["status", "updated_at"])
                _deliver(request, parent, invitation.email)
                record_activity(
                    parent, f"Resent the new family invitation for {invitation.email}."
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
