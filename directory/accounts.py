"""Account identity and the boundary between authentication and family access."""

from urllib.parse import urlsplit

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.account.utils import perform_login
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import Http404
from django.urls import reverse


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # Only FrontPorch's email-bound invitations may create accounts.
        return False

    def get_reset_password_from_key_url(self, key):
        url = super().get_reset_password_from_key_url(key)
        if settings.FRONTPORCH_PUBLIC_URL:
            return settings.FRONTPORCH_PUBLIC_URL.rstrip("/") + urlsplit(url).path
        return url


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def get_provider(self, request, provider, client_id=None):
        try:
            return super().get_provider(request, provider, client_id=client_id)
        except SocialApp.DoesNotExist as error:
            raise Http404("This sign-in provider is not configured.") from error

    def is_open_for_signup(self, request, sociallogin):
        return False

    def can_authenticate_by_email(self, login, email):
        # Never choose between ambiguous legacy/admin-created identities.
        if login.account.provider not in {"google", "apple"}:
            return False
        users = list(get_user_model().objects.filter(email__iexact=email)[:2])
        if len(users) != 1 or not users[0].is_active:
            return False
        if (
            EmailAddress.objects.filter(email__iexact=email)
            .exclude(user_id=users[0].pk)
            .exists()
        ):
            return False
        return super().can_authenticate_by_email(login, email)


def account_email_in_use(email, *, user_id=None):
    return bool(email) and (
        get_user_model()
        .objects.filter(email__iexact=email)
        .exclude(pk=user_id)
        .exists()
        or EmailAddress.objects.filter(email__iexact=email)
        .exclude(user_id=user_id)
        .exists()
    )


def validate_account_email(email, *, user_id=None):
    email = email.strip().lower()
    if account_email_in_use(email, user_id=user_id):
        raise ValidationError("An account already uses this email.")
    return email


def sync_account_email(user, *, verified=False):
    """Used by invitations and private admin; allauth owns self-service changes."""
    EmailAddress.objects.filter(user=user).exclude(email__iexact=user.email).delete()
    if user.email:
        address, _ = EmailAddress.objects.get_or_create(
            user=user,
            email=user.email.lower(),
            defaults={"primary": True, "verified": verified},
        )
        address.primary = True
        address.verified = address.verified or verified
        address.save(update_fields=["primary", "verified"])


def login_after_invitation(request, user):
    # Possession and successful redemption of the email-bound token proves ownership.
    sync_account_email(user, verified=True)
    return perform_login(
        request,
        user,
        email_verification="optional",
        redirect_url=reverse("directory:dashboard"),
    )
