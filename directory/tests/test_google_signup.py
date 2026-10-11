import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from allauth.account.models import EmailAddress
from allauth.core import context
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from directory.forms import InvitedSocialSignupForm
from directory.models import (
    ChildConnection,
    ConnectionInvitation,
    Family,
    FamilyActivity,
    FamilyInvitation,
    Parent,
)
from directory.tests import test_accounts


@override_settings(SOCIALACCOUNT_PROVIDERS=test_accounts.PROVIDERS)
class GoogleSignupTests(test_accounts.AccountFixture):
    social_login = test_accounts.SocialLoginTests.social_login

    def setUp(self):
        super().setUp()
        self.token = "fictional-family-invitation"
        self.invitation = FamilyInvitation.objects.create(
            family=self.parent.family,
            invited_by=self.parent,
            email="new@example.com",
            token_digest=hashlib.sha256(self.token.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.invite_url = reverse("directory:register_invited", args=[self.token])
        self.signup_url = reverse("socialaccount_signup")
        self.data = {"family_name": "Willow", "display_name": "Morgan"}

    def begin_signup(self):
        request, response = self.social_login(
            "google", "NEW@example.com", next_url=self.invite_url
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.signup_url)
        request.session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = request.session.session_key
        return request

    def assert_not_created(self):
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Family.objects.count(), 1)
        self.assertEqual(Parent.objects.count(), 1)
        self.assertFalse(SocialAccount.objects.exists())

    def test_invitation_offers_google_with_bound_return_path_and_csrf(self):
        page = self.client.get(self.invite_url)
        self.assertContains(page, "Continue with Google")
        self.assertNotContains(page, "Continue with Apple")
        self.assertContains(page, f'name="next" value="{self.invite_url}"')
        self.assertContains(page, 'name="password1"')
        response = self.client.post(reverse("google_login"), {"next": self.invite_url})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(self.token, response.url)
        self.assertIn(
            self.invite_url, str(self.client.session.get("socialaccount_states"))
        )
        self.assertEqual(
            Client(enforce_csrf_checks=True).post(reverse("google_login")).status_code,
            403,
        )

    def test_google_hidden_without_configuration(self):
        for providers in ({}, {"apple": test_accounts.PROVIDERS["apple"]}):
            with (
                self.subTest(providers=providers),
                override_settings(SOCIALACCOUNT_PROVIDERS=providers),
            ):
                response = self.client.get(self.invite_url)
                self.assertNotContains(response, "Continue with Google")
                self.assertNotContains(response, "To sign up with Google")

    def test_oauth_callback_preserves_invitation_and_rejects_replayed_state(self):
        response = self.client.post(reverse("google_login"), {"next": self.invite_url})
        state = parse_qs(urlsplit(response.url).query)["state"][0]

        def provider_response(adapter, request, app, token, **kwargs):
            return SocialLogin(
                user=User(email=self.invitation.email),
                account=SocialAccount(provider="google", uid="new-google-user"),
                email_addresses=[
                    EmailAddress(
                        email=self.invitation.email, verified=True, primary=True
                    )
                ],
                provider=adapter.get_provider(),
            )

        with (
            patch(
                "allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token",
                return_value={
                    "access_token": "fictional-test-token",
                    "token_type": "Bearer",
                },
            ),
            patch(
                "allauth.socialaccount.providers.google.views.GoogleOAuth2Adapter.complete_login",
                autospec=True,
                side_effect=provider_response,
            ),
        ):
            callback = reverse("google_callback")
            response = self.client.get(
                callback, {"state": state, "code": "fictional-code"}
            )
            self.assertRedirects(response, self.signup_url)
            self.assert_not_created()
            response = self.client.get(
                callback, {"state": state, "code": "fictional-code"}
            )
            self.assertNotEqual(response.status_code, 302)
            self.assert_not_created()
        self.assertRedirects(
            self.client.post(self.signup_url, self.data), reverse("directory:dashboard")
        )

    def test_google_creates_family_without_password_only_after_details(self):
        self.begin_signup()
        self.assert_not_created()
        page = self.client.get(self.signup_url)
        self.assertContains(page, "The Maple family invited you")
        self.assertContains(page, 'name="family_name"')
        self.assertNotContains(page, 'name="password1"')
        self.assertNotContains(page, 'name="password2"')
        self.assertNotContains(page, 'name="username"')
        response = self.client.post(
            self.signup_url, {**self.data, "email": "attacker@example.com"}
        )
        self.assertRedirects(response, reverse("directory:dashboard"))
        user = User.objects.get(email="new@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(self.client.session[SESSION_KEY], str(user.pk))
        self.assertEqual(SocialAccount.objects.get().user, user)
        self.assertTrue(EmailAddress.objects.get(user=user).verified)
        parent = user.frontporch_parent
        self.assertTrue(parent.is_guardian)
        self.assertTrue(parent.is_primary)
        self.assertEqual(parent.display_name, "Morgan")
        self.assertEqual(parent.family.name, "Willow")
        self.assertFalse(parent.family.directory_listed)
        self.assertFalse(parent.directory_visible)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, "accepted")
        self.assertEqual(self.invitation.accepted_family, parent.family)
        self.assertTrue(FamilyActivity.objects.filter(family=parent.family).exists())
        self.assertTrue(
            FamilyActivity.objects.filter(
                family=self.parent.family, description__contains="accepted"
            ).exists()
        )
        self.assertFalse(ChildConnection.objects.exists())
        self.assertFalse(ConnectionInvitation.objects.exists())
        self.client.logout()
        request, _ = self.social_login("google", user.email)
        self.assertEqual(request.session[SESSION_KEY], str(user.pk))
        self.assertEqual(self.client.get(self.invite_url).status_code, 410)

    def test_directory_listing_requires_opt_in(self):
        self.begin_signup()
        self.client.post(self.signup_url, {**self.data, "directory_listed": "on"})
        parent = Parent.objects.get(user__email=self.invitation.email)
        self.assertTrue(parent.family.directory_listed)
        self.assertTrue(parent.directory_visible)

    def test_invalid_family_details_preserve_pending_signup(self):
        self.begin_signup()
        response = self.client.post(self.signup_url, {"family_name": "Maple"})
        self.assertContains(response, "A family with this name already exists.")
        self.assertContains(response, "This field is required.")
        self.assert_not_created()
        self.invitation.refresh_from_db()
        self.assertTrue(self.invitation.available)
        self.assertRedirects(
            self.client.post(self.signup_url, self.data), reverse("directory:dashboard")
        )

    def test_provider_email_and_invitation_are_required(self):
        cases = [
            ("google", "wrong@example.com", True, self.invite_url),
            ("google", self.invitation.email, False, self.invite_url),
            ("apple", self.invitation.email, True, self.invite_url),
            ("google", self.invitation.email, True, None),
            ("google", self.invitation.email, True, "/register/not-a-token/"),
            ("google", self.invitation.email, True, "/register/"),
            (
                "google",
                self.invitation.email,
                True,
                "https://untrusted.example.com" + self.invite_url,
            ),
        ]
        for provider, email, verified, next_url in cases:
            with self.subTest(provider=provider, email=email, next_url=next_url):
                request, response = self.social_login(
                    provider, email, verified=verified, next_url=next_url
                )
                self.assertContains(response, "Your invitation comes first.")
                self.assertNotIn(SESSION_KEY, request.session)
                self.assert_not_created()

    def test_unavailable_invitation_denied_at_callback_and_final_submission(self):
        changes = [
            {"status": "cancelled"},
            {"status": "replaced"},
            {"status": "accepted"},
            {"expires_at": timezone.now() - timedelta(seconds=1)},
        ]
        for change in changes:
            with self.subTest(change=change):
                FamilyInvitation.objects.filter(pk=self.invitation.pk).update(
                    status="pending", expires_at=timezone.now() + timedelta(days=1)
                )
                self.begin_signup()
                FamilyInvitation.objects.filter(pk=self.invitation.pk).update(**change)
                self.assertContains(
                    self.client.post(self.signup_url, self.data),
                    "Your invitation comes first.",
                )
                _, response = self.social_login(
                    "google", self.invitation.email, next_url=self.invite_url
                )
                self.assertContains(response, "Your invitation comes first.")
                self.assert_not_created()

    def test_revoked_sponsor_and_registration_switch_block_pending_signup(self):
        self.begin_signup()
        self.parent.is_guardian = False
        self.parent.save()
        self.assertContains(
            self.client.post(self.signup_url, self.data), "Your invitation comes first."
        )
        self.parent.is_guardian = True
        self.parent.save()
        with override_settings(FRONTPORCH_ALLOW_REGISTRATION=False):
            self.assertContains(
                self.client.post(self.signup_url, self.data),
                "Your invitation comes first.",
            )
        self.assert_not_created()

    def test_email_claimed_during_signup_does_not_replace_account(self):
        self.begin_signup()
        user = User.objects.create_user(
            "claimed", self.invitation.email, "original-pass"
        )
        self.assertContains(
            self.client.post(self.signup_url, self.data),
            "An account already uses this email.",
        )
        self.assertFalse(SocialAccount.objects.exists())
        self.assertEqual(Family.objects.count(), 1)
        user.refresh_from_db()
        self.assertTrue(user.check_password("original-pass"))

    def test_stale_validated_form_cannot_redeem_cancelled_invitation(self):
        request = self.begin_signup()
        with context.request_context(request):
            login = SocialLogin.deserialize(
                request.session["socialaccount_sociallogin"]
            )
            form = InvitedSocialSignupForm(self.data, sociallogin=login)
            self.assertTrue(form.is_valid(), form.errors)
            FamilyInvitation.objects.filter(pk=self.invitation.pk).update(
                status="cancelled"
            )
            with self.assertRaises(ValidationError):
                form.save(request)
        self.assert_not_created()

    def test_failure_rolls_back_social_account_and_allows_retry(self):
        self.begin_signup()
        with patch(
            "directory.registration.Parent.objects.create",
            side_effect=ValidationError("Please try again."),
        ):
            self.assertContains(
                self.client.post(self.signup_url, self.data), "Please try again."
            )
        self.assert_not_created()
        self.invitation.refresh_from_db()
        self.assertTrue(self.invitation.available)
        self.assertRedirects(
            self.client.post(self.signup_url, self.data), reverse("directory:dashboard")
        )

    @override_settings(ROOT_URLCONF="frontporch.public_urls")
    def test_google_signup_works_on_public_portal(self):
        self.begin_signup()
        self.assertRedirects(
            self.client.post(self.signup_url, self.data), reverse("directory:dashboard")
        )
