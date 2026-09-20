import re
from urllib.parse import urlsplit

from allauth.account.models import EmailAddress
from allauth.core import context
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.middleware import AuthenticationMiddleware
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from directory.accounts import sync_account_email
from directory.models import Family, Parent


PROVIDERS = {
    provider: {
        "APP": {"client_id": "test-client", "secret": "test-secret", "key": "test-key"},
        "EMAIL_AUTHENTICATION": True,
        "OAUTH_PKCE_ENABLED": True,
    }
    for provider in ("google", "apple")
}


class AccountFixture(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            "taylor", "taylor@example.com", "original-account-password"
        )
        self.parent = Parent.objects.create(
            family=Family.objects.create(name="Maple"),
            user=self.user,
            display_name="Taylor",
        )
        sync_account_email(self.user)


class AccountTests(AccountFixture):
    def test_guardian_requires_one_protected_account(self):
        with self.assertRaises(ValidationError):
            Parent.objects.create(family=self.parent.family, display_name="Morgan")
        with self.assertRaises(ValidationError):
            Parent.objects.create(
                family=self.parent.family, display_name="Morgan", user=self.user
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Parent.objects.filter(pk=self.parent.pk).update(user=None)
        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_guardian_email_always_comes_from_account(self):
        self.user.email = "new@example.com"
        self.user.save(update_fields=["email"])
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.email, "new@example.com")
        self.client.force_login(self.user)
        page = self.client.get(reverse("directory:settings"))
        self.assertContains(page, "new@example.com")
        self.assertNotContains(page, "taylor@example.com")

    def test_email_change_updates_guardian_only_after_verification(self):
        sync_account_email(self.user, verified=True)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("account_email"),
            {"email": "new@example.com", "action_add": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "taylor@example.com")
        address = EmailAddress.objects.get(email="new@example.com")
        self.assertFalse(address.verified)
        confirmation = re.search(
            r"https?://[^\s]+/accounts/confirm-email/\S+", mail.outbox[-1].body
        ).group(0)
        path = urlsplit(confirmation).path
        self.client.get(path)
        address.refresh_from_db()
        self.assertFalse(address.verified)
        self.client.post(path)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.email, "new@example.com")
        self.assertFalse(
            EmailAddress.objects.filter(email="taylor@example.com").exists()
        )

    def test_allauth_login_accepts_username_and_case_insensitive_email(self):
        for identifier in ("taylor", "TAYLOR@example.com"):
            with self.subTest(identifier=identifier):
                self.client.logout()
                response = self.client.post(
                    reverse("account_login"),
                    {"login": identifier, "password": "original-account-password"},
                )
                self.assertRedirects(response, reverse("directory:dashboard"))
                self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))

    def test_bad_password_and_inactive_account_cannot_login(self):
        self.client.post(
            reverse("account_login"), {"login": self.user.email, "password": "wrong"}
        )
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": "original-account-password"},
        )
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_login_rejects_external_redirect_and_logout_requires_post(self):
        response = self.client.post(
            reverse("account_login"),
            {
                "login": self.user.email,
                "password": "original-account-password",
                "next": "https://untrusted.example.com/",
            },
        )
        self.assertRedirects(response, reverse("directory:dashboard"))
        self.client.get(reverse("account_logout"))
        self.assertIn(SESSION_KEY, self.client.session)
        self.client.post(reverse("account_logout"))
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_default_allauth_signup_cannot_bypass_invitations(self):
        for method in (self.client.get, self.client.post):
            response = method(
                reverse("account_signup"),
                {"email": "uninvited@example.com", "password1": "password-123"},
            )
            self.assertContains(response, "Your invitation comes first.")
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Parent.objects.count(), 1)

    @override_settings(FRONTPORCH_PUBLIC_URL="https://porch.example.com")
    def test_password_reset_uses_public_host_and_token_is_single_use(self):
        response = self.client.post(
            reverse("account_reset_password"), {"email": self.user.email}
        )
        self.assertRedirects(response, reverse("account_reset_password_done"))
        reset_url = re.search(
            r"https://porch\.example\.com/accounts/password/reset/key/\S+",
            mail.outbox[-1].body,
        ).group(0)
        reset_path = urlsplit(reset_url).path
        response = self.client.get(reset_path)
        self.assertEqual(response.status_code, 302)
        password_path = response.url
        self.assertContains(self.client.get(password_path), "Change Password")
        response = self.client.post(
            password_path,
            {
                "password1": "new-unguessable-password-456",
                "password2": "new-unguessable-password-456",
            },
        )
        self.assertRedirects(response, reverse("account_reset_password_from_key_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-unguessable-password-456"))
        self.assertContains(Client().get(reset_path, follow=True), "Bad Token")

    def test_admin_exposes_email_on_creation_and_keeps_allauth_consistent(self):
        operator = User.objects.create_superuser(
            "operator", "op@example.com", "operator-pass"
        )
        self.client.force_login(operator)
        self.assertContains(
            self.client.get(reverse("admin:auth_user_add")), 'name="email"'
        )
        change_url = reverse("admin:auth_user_change", args=[self.user.pk])
        response = self.client.post(
            change_url,
            {
                "username": self.user.username,
                "email": "NEW@example.com",
                "is_active": "on",
                "date_joined_0": "2026-09-19",
                "date_joined_1": "10:00:00",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        address = EmailAddress.objects.get(user=self.user)
        self.assertEqual(address.email, self.user.email)
        self.assertFalse(address.verified)
        duplicate = self.client.post(
            change_url,
            {
                "username": self.user.username,
                "email": "OP@example.com",
                "is_active": "on",
                "date_joined_0": "2026-09-19",
                "date_joined_1": "10:00:00",
            },
        )
        self.assertContains(duplicate, "An account already uses this email.")

    def test_admin_can_create_account_with_email_before_linking_guardian(self):
        operator = User.objects.create_superuser(
            "operator", "op@example.com", "operator-pass"
        )
        self.client.force_login(operator)
        response = self.client.post(
            reverse("admin:auth_user_add"),
            {
                "username": "morgan",
                "email": "MORGAN@example.com",
                "usable_password": "true",
                "password1": "new-guardian-password-456",
                "password2": "new-guardian-password-456",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="morgan")
        self.assertEqual(user.email, "morgan@example.com")
        self.assertTrue(user.check_password("new-guardian-password-456"))
        self.assertEqual(EmailAddress.objects.get(user=user).email, user.email)


@override_settings(SOCIALACCOUNT_PROVIDERS=PROVIDERS)
class SocialLoginTests(AccountFixture):
    def social_login(
        self,
        provider_id,
        email,
        *,
        verified=True,
        user=None,
        uid="provider-user",
        process="login",
    ):
        request = RequestFactory().get(f"/accounts/{provider_id}/login/callback/")
        SessionMiddleware(lambda request: None).process_request(request)
        AuthenticationMiddleware(lambda request: None).process_request(request)
        MessageMiddleware(lambda request: None).process_request(request)
        request.user = user or AnonymousUser()
        with context.request_context(request):
            provider = get_adapter().get_provider(request, provider_id)
            login = SocialLogin(
                user=User(email=email),
                account=SocialAccount(provider=provider_id, uid=uid),
                email_addresses=[
                    EmailAddress(email=email, verified=verified, primary=True)
                ],
                provider=provider,
            )
            login.state = {"process": process}
            response = complete_social_login(request, login)
        return request, response

    def test_configured_providers_have_post_buttons(self):
        page = self.client.get(reverse("account_login"))
        self.assertContains(page, "Continue with Google")
        self.assertContains(page, "Continue with Apple")
        self.assertContains(
            page, 'method="post" action="/accounts/google/login/?process=login"'
        )
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("google_login")).status_code, 403)
        self.assertContains(client.get(reverse("google_login")), "Google")

    def test_verified_google_and_apple_match_only_existing_account(self):
        for provider in ("google", "apple"):
            with self.subTest(provider=provider):
                request, response = self.social_login(provider, "TAYLOR@example.com")
                self.assertEqual(response.status_code, 302)
                self.assertEqual(request.session[SESSION_KEY], str(self.user.pk))
                self.assertTrue(
                    SocialAccount.objects.filter(
                        user=self.user, provider=provider
                    ).exists()
                )
                self.assertEqual(User.objects.count(), 1)
                self.assertEqual(Parent.objects.count(), 1)

    def test_unverified_email_and_uninvited_people_cannot_get_accounts(self):
        for provider in ("google", "apple"):
            for email, verified in (
                (self.user.email, False),
                ("outsider@example.com", True),
            ):
                with self.subTest(provider=provider, email=email):
                    request, response = self.social_login(
                        provider, email, verified=verified
                    )
                    self.assertNotIn(SESSION_KEY, request.session)
                    self.assertContains(response, "Your invitation comes first.")
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(SocialAccount.objects.exists())

    def test_ambiguous_email_cannot_choose_a_family(self):
        User.objects.create_user(
            "duplicate", "TAYLOR@example.com", "duplicate-password"
        )
        request, _ = self.social_login("google", self.user.email)
        self.assertNotIn(SESSION_KEY, request.session)
        self.assertFalse(SocialAccount.objects.exists())

    def test_inactive_account_cannot_login_or_auto_connect(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        request, _ = self.social_login("apple", self.user.email)
        self.assertNotIn(SESSION_KEY, request.session)
        self.assertFalse(SocialAccount.objects.exists())

    def test_apple_private_email_can_be_connected_after_password_login(self):
        relay_email = "hidden@privaterelay.appleid.com"
        request, _ = self.social_login("apple", relay_email)
        self.assertNotIn(SESSION_KEY, request.session)
        _, response = self.social_login(
            "apple", relay_email, user=self.user, process="connect"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SocialAccount.objects.get(provider="apple").user, self.user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "taylor@example.com")
        request, _ = self.social_login("apple", relay_email)
        self.assertEqual(request.session[SESSION_KEY], str(self.user.pk))

    def test_removed_guardian_cannot_regain_access_through_google(self):
        self.parent.is_guardian = False
        self.parent.save()
        request, _ = self.social_login("google", self.user.email)
        self.assertEqual(request.session[SESSION_KEY], str(self.user.pk))
        self.user.refresh_from_db()
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(reverse("directory:dashboard")).status_code, 403
        )
        self.parent.refresh_from_db()
        self.assertFalse(self.parent.is_guardian)

    def test_google_authorization_redirect_requests_state_and_pkce(self):
        response = self.client.post(reverse("google_login"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response.url).hostname, "accounts.google.com")
        self.assertIn("state=", response.url)
        self.assertIn("code_challenge=", response.url)


class UnconfiguredProviderTests(TestCase):
    def test_no_buttons_without_credentials(self):
        with override_settings(SOCIALACCOUNT_PROVIDERS={}):
            response = self.client.get(reverse("account_login"))
        self.assertNotContains(response, "Continue with Google")
        self.assertNotContains(response, "Continue with Apple")

    def test_unconfigured_provider_url_returns_not_found(self):
        with override_settings(SOCIALACCOUNT_PROVIDERS={}):
            self.assertEqual(self.client.post(reverse("google_login")).status_code, 404)
