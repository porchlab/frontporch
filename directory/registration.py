"""Shared policy for password and Google family invitation acceptance."""

import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import Resolver404, resolve

from .models import Family, FamilyInvitation, Parent


def social_signup_invitation(sociallogin):
    # The return path is carried in allauth's server-side OAuth state. Never
    # accept an invitation or email supplied by the signup form instead.
    if (
        not settings.FRONTPORCH_ALLOW_REGISTRATION
        or sociallogin.account.provider != "google"
        or sociallogin.is_existing
        or sociallogin.state.get("process") not in {"login", "signup"}
    ):
        return None
    path = sociallogin.state.get("next") or ""
    try:
        match = resolve(path)
    except Resolver404:
        return None
    if match.view_name != "directory:register_invited":
        return None
    invitation = (
        FamilyInvitation.objects.select_related("family", "invited_by__user")
        .filter(token_digest=hashlib.sha256(match.kwargs["token"].encode()).hexdigest())
        .first()
    )
    if (
        invitation
        and invitation.available
        and any(
            address.verified and address.email.lower() == invitation.email.lower()
            for address in sociallogin.email_addresses
        )
    ):
        return invitation
    return None


def lock_registration_invitation(invitation, email):
    """Caller must hold a transaction through account and family creation."""
    from .accounts import validate_account_email
    from .services import lock_email_identity

    Family.objects.select_for_update().get(pk=invitation.family_id)
    invitation = FamilyInvitation.objects.select_for_update().get(pk=invitation.pk)
    if (
        not settings.FRONTPORCH_ALLOW_REGISTRATION
        or not invitation.available
        or invitation.email != email
    ):
        raise ValidationError(
            "This invitation is no longer available. Ask an existing family for a new invitation."
        )
    lock_email_identity(email)
    validate_account_email(email)
    return invitation


def create_invited_family(user, invitation, data):
    """Finish acceptance inside the transaction that creates the account."""
    from .accounts import sync_account_email
    from .services import record_activity

    family = Family.objects.create(
        name=data["family_name"], directory_listed=data["directory_listed"]
    )
    parent = Parent.objects.create(
        user=user,
        family=family,
        display_name=data["display_name"],
        phone=data["phone"],
        is_guardian=True,
        is_primary=True,
        directory_visible=data["directory_listed"],
    )
    sync_account_email(user, verified=True)
    invitation.status = "accepted"
    invitation.accepted_family = family
    invitation.save(update_fields=["status", "accepted_family", "updated_at"])
    record_activity(parent, "Your family account is ready.")
    record_activity(
        invitation.invited_by,
        f"The {family.name} family accepted your invitation to FrontPorch.",
    )
