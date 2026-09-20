import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from directory.forms import ParentRegistrationForm
from directory.models import (
    AllowedChildFamilyRelationship,
    ChildConnection,
    ConnectionInvitation,
    Family,
    FamilyActivity,
    FamilyInvitation,
    Parent,
)


class FamilyInvitationTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Maple")
        self.user = User.objects.create_user(
            "guardian", "maple@example.com", "test-password-123"
        )
        # Deliberately neither staff nor the primary guardian.
        self.parent = Parent.objects.create(
            user=self.user,
            family=self.family,
            display_name="Taylor",
        )
        self.client.force_login(self.user)
        self.signup_data = {
            "email": "new@example.com",
            "family_name": "Willow",
            "display_name": "Morgan",
            "password1": "different-test-pass-123",
            "password2": "different-test-pass-123",
        }

    def invite(self, email="new@example.com"):
        response = self.client.post(
            reverse("directory:family_invite"), {"email": email}
        )
        self.assertRedirects(response, reverse("directory:settings"))
        invitation = FamilyInvitation.objects.order_by("-pk").first()
        token = re.search(r"/register/([^/]+)/", mail.outbox[-1].body).group(1)
        return invitation, token

    def test_any_guardian_can_invite_and_email_is_bound_without_exposing_token(self):
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.parent.is_primary)
        invitation, token = self.invite("NEW@example.com")
        self.assertEqual(invitation.email, "new@example.com")
        self.assertEqual(invitation.invited_by, self.parent)
        self.assertEqual(invitation.family, self.family)
        self.assertEqual(
            invitation.token_digest, hashlib.sha256(token.encode()).hexdigest()
        )
        self.assertEqual(mail.outbox[-1].to, ["new@example.com"])
        self.assertEqual(Family.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)
        settings_page = self.client.get(reverse("directory:settings"))
        self.assertContains(settings_page, "Invite a new family")
        self.assertContains(settings_page, "new@example.com")
        self.assertNotContains(settings_page, token)
        self.assertNotContains(settings_page, invitation.token_digest)
        self.assertContains(
            self.client.get(reverse("directory:family_directory")),
            "Invite a new family",
        )
        self.assertTrue(
            FamilyActivity.objects.filter(family=self.family, actor=self.user).exists()
        )

    def test_registration_creates_separate_family_once_and_no_calling_permissions(self):
        invitation, token = self.invite()
        self.client.logout()
        url = reverse("directory:register_invited", args=[token])
        page = self.client.get(url)
        self.assertContains(page, "The Maple family invited you")
        self.assertIn("no-store", page.headers["Cache-Control"])
        self.assertEqual(page.headers["Referrer-Policy"], "same-origin")
        self.assertRedirects(
            self.client.post(url, self.signup_data), reverse("directory:dashboard")
        )
        parent = Parent.objects.get(user__email="new@example.com")
        self.assertNotEqual(parent.family_id, self.family.pk)
        self.assertTrue(parent.is_primary)
        self.assertTrue(parent.is_guardian)
        self.assertFalse(parent.family.directory_listed)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "accepted")
        self.assertEqual(invitation.accepted_family, parent.family)
        self.assertTrue(FamilyActivity.objects.filter(family=parent.family).exists())
        self.assertTrue(
            FamilyActivity.objects.filter(
                family=self.family, description__contains="accepted"
            ).exists()
        )
        self.assertFalse(ChildConnection.objects.exists())
        self.assertFalse(ConnectionInvitation.objects.exists())
        self.assertFalse(AllowedChildFamilyRelationship.objects.exists())
        self.client.logout()
        self.assertEqual(
            self.client.post(
                url, {**self.signup_data, "family_name": "Oak"}
            ).status_code,
            410,
        )
        self.assertEqual(Family.objects.count(), 2)
        # Newly registered families can invite the next household too.
        self.client.force_login(parent.user)
        self.invite("another@example.com")

    def test_uninvited_signup_invalid_token_and_discovery_code_are_denied(self):
        self.client.logout()
        for url in (
            reverse("directory:register"),
            reverse("directory:register_invited", args=["made-up-token"]),
            reverse("directory:register_invited", args=[self.family.invite_code]),
        ):
            for method in (self.client.get, self.client.post):
                with self.subTest(url=url, method=method):
                    response = method(url, self.signup_data)
                    self.assertEqual(response.status_code, 404)
                    self.assertNotContains(
                        response, 'name="password1"', status_code=404
                    )
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Family.objects.count(), 1)
        for url in (reverse("directory:welcome"), reverse("login")):
            page = self.client.get(url)
            self.assertNotContains(page, 'href="/register/"')
            self.assertContains(page, "invite only", html=False)

    def test_submitted_email_cannot_override_invited_email(self):
        invitation, token = self.invite()
        self.client.logout()
        response = self.client.post(
            reverse("directory:register_invited", args=[token]),
            {**self.signup_data, "email": "different@example.com"},
        )
        self.assertRedirects(response, reverse("directory:dashboard"))
        self.assertTrue(User.objects.filter(email=invitation.email).exists())
        self.assertFalse(User.objects.filter(email="different@example.com").exists())

    def test_invalid_form_does_not_consume_invitation(self):
        invitation, token = self.invite()
        self.client.logout()
        response = self.client.post(
            reverse("directory:register_invited", args=[token]),
            {**self.signup_data, "password2": "does-not-match"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        invitation.refresh_from_db()
        self.assertTrue(invitation.available)
        self.assertEqual(Family.objects.count(), 1)

    def test_cancel_resend_and_expiry_invalidate_old_links(self):
        invitation, token = self.invite()
        response = self.client.post(
            reverse(
                "directory:family_invitation_action", args=[invitation.pk, "resend"]
            )
        )
        self.assertRedirects(response, reverse("directory:settings"))
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "replaced")
        replacement = FamilyInvitation.objects.get(status="pending")
        replacement_token = re.search(
            r"/register/([^/]+)/", mail.outbox[-1].body
        ).group(1)
        self.assertNotEqual(token, replacement_token)
        anonymous = Client()
        for method in (anonymous.get, anonymous.post):
            self.assertEqual(
                method(reverse("directory:register_invited", args=[token])).status_code,
                410,
            )
        replacement.expires_at = timezone.now() - timedelta(seconds=1)
        replacement.save()
        self.assertEqual(
            anonymous.post(
                reverse("directory:register_invited", args=[replacement_token]),
                self.signup_data,
            ).status_code,
            410,
        )
        self.client.post(
            reverse(
                "directory:family_invitation_action", args=[replacement.pk, "cancel"]
            )
        )
        replacement.refresh_from_db()
        self.assertEqual(replacement.status, "cancelled")
        replacement.expires_at = timezone.now() + timedelta(days=7)
        replacement.save()
        self.assertEqual(
            anonymous.post(
                reverse("directory:register_invited", args=[replacement_token]),
                self.signup_data,
            ).status_code,
            410,
        )

    def test_removed_or_inactive_inviter_cannot_sponsor_registration(self):
        invitation, token = self.invite()
        self.client.logout()
        self.parent.is_guardian = False
        self.parent.save()
        url = reverse("directory:register_invited", args=[token])
        self.assertEqual(self.client.post(url, self.signup_data).status_code, 410)
        self.parent.is_guardian = True
        self.parent.save()
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.post(url, self.signup_data).status_code, 410)
        self.assertEqual(Family.objects.count(), 1)

    def test_existing_account_or_duplicate_pending_invite_is_rejected(self):
        self.assertContains(
            self.client.post(
                reverse("directory:family_invite"), {"email": self.user.email.upper()}
            ),
            "already has an account",
        )
        self.assertFalse(FamilyInvitation.objects.exists())
        self.invite()
        self.assertContains(
            self.client.post(
                reverse("directory:family_invite"), {"email": "NEW@example.com"}
            ),
            "already has an invitation",
        )
        self.assertEqual(FamilyInvitation.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_account_created_after_invitation_cannot_be_replaced(self):
        invitation, token = self.invite()
        existing = User.objects.create_user(
            "existing", "NEW@example.com", "test-password-123"
        )
        self.client.logout()
        response = self.client.post(
            reverse("directory:register_invited", args=[token]), self.signup_data
        )
        self.assertContains(response, "already uses this email")
        existing.refresh_from_db()
        self.assertTrue(existing.check_password("test-password-123"))
        invitation.refresh_from_db()
        self.assertTrue(invitation.available)
        self.assertEqual(Family.objects.count(), 1)

    def test_email_failure_rolls_back_send_and_preserves_original_on_resend(self):
        with patch(
            "directory.family_invitations.send_mail", side_effect=OSError("offline")
        ):
            response = self.client.post(
                reverse("directory:family_invite"), {"email": "new@example.com"}
            )
        self.assertContains(response, "could not be emailed")
        self.assertFalse(FamilyInvitation.objects.exists())
        self.assertFalse(FamilyActivity.objects.exists())
        invitation, token = self.invite()
        with patch("directory.family_invitations.send_mail", return_value=0):
            response = self.client.post(
                reverse(
                    "directory:family_invitation_action", args=[invitation.pk, "resend"]
                ),
                follow=True,
            )
        self.assertContains(response, "original invitation has not been changed")
        invitation.refresh_from_db()
        self.assertTrue(invitation.available)
        self.assertEqual(FamilyInvitation.objects.count(), 1)
        self.assertEqual(
            Client()
            .get(reverse("directory:register_invited", args=[token]))
            .status_code,
            200,
        )

    def test_invite_management_requires_guardian_and_is_scoped_to_sponsoring_family(
        self,
    ):
        invitation, token = self.invite()
        invite_url = reverse("directory:family_invite")
        action_url = reverse(
            "directory:family_invitation_action", args=[invitation.pk, "cancel"]
        )
        self.client.logout()
        self.assertEqual(self.client.post(invite_url).status_code, 302)
        self.assertEqual(self.client.post(action_url).status_code, 302)
        self.client.force_login(self.user)
        self.parent.is_guardian = False
        self.parent.save()
        self.assertEqual(self.client.post(invite_url).status_code, 403)
        self.assertEqual(self.client.post(action_url).status_code, 403)
        other_family = Family.objects.create(name="Oak")
        other_user = User.objects.create_user(
            "other", "other@example.com", "test-password-123"
        )
        Parent.objects.create(
            user=other_user, family=other_family, display_name="Rowan"
        )
        self.client.force_login(other_user)
        self.assertNotContains(
            self.client.get(reverse("directory:settings")), "new@example.com"
        )
        for action in ("cancel", "resend"):
            self.assertEqual(
                self.client.post(
                    reverse(
                        "directory:family_invitation_action",
                        args=[invitation.pk, action],
                    )
                ).status_code,
                404,
            )
        # Any active guardian of the sponsoring family can manage its invitations.
        other_user.frontporch_parent.family = self.family
        other_user.frontporch_parent.save()
        self.assertEqual(self.client.get(action_url).status_code, 405)
        self.assertRedirects(
            self.client.post(action_url), reverse("directory:settings")
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "cancelled")

    def test_csrf_required_to_send_cancel_and_redeem(self):
        invitation, token = self.invite()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(
            client.post(
                reverse("directory:family_invite"), {"email": "another@example.com"}
            ).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                reverse(
                    "directory:family_invitation_action", args=[invitation.pk, "cancel"]
                )
            ).status_code,
            403,
        )
        client.logout()
        self.assertEqual(
            client.post(
                reverse("directory:register_invited", args=[token]), self.signup_data
            ).status_code,
            403,
        )

    def test_stale_validated_form_cannot_redeem_cancelled_invitation(self):
        invitation, token = self.invite()
        form = ParentRegistrationForm(self.signup_data, invitation=invitation)
        self.assertTrue(form.is_valid(), form.errors)
        FamilyInvitation.objects.filter(pk=invitation.pk).update(status="cancelled")
        with self.assertRaisesMessage(ValidationError, "no longer available"):
            form.save()
        self.assertEqual(Family.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    def test_failed_registration_rolls_back_account_and_invitation(self):
        invitation, token = self.invite()
        self.client.logout()
        with patch(
            "directory.forms.Parent.objects.create",
            side_effect=ValidationError("Please try again."),
        ):
            response = self.client.post(
                reverse("directory:register_invited", args=[token]), self.signup_data
            )
        self.assertContains(response, "Please try again.")
        invitation.refresh_from_db()
        self.assertTrue(invitation.available)
        self.assertEqual(Family.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    def test_registration_switch_can_disable_even_valid_invitations(self):
        invitation, token = self.invite()
        with override_settings(FRONTPORCH_ALLOW_REGISTRATION=False):
            self.assertEqual(
                self.client.post(
                    reverse("directory:family_invite"), {"email": "another@example.com"}
                ).status_code,
                404,
            )
            self.client.logout()
            self.assertEqual(
                self.client.post(
                    reverse("directory:register_invited", args=[token]),
                    self.signup_data,
                ).status_code,
                404,
            )


class FamilyInvitationConcurrencyTests(TransactionTestCase):
    def test_two_validated_submissions_can_only_redeem_once(self):
        family = Family.objects.create(name="Maple")
        user = User.objects.create_user(
            "inviter", "inviter@example.com", "test-password-123"
        )
        parent = Parent.objects.create(user=user, family=family, display_name="Taylor")
        invitation = FamilyInvitation.objects.create(
            family=family,
            invited_by=parent,
            email="new@example.com",
            token_digest=hashlib.sha256(b"test-invitation").hexdigest(),
            expires_at=timezone.now() + timedelta(days=7),
        )
        barrier = Barrier(2)

        def register(family_name):
            close_old_connections()
            try:
                form = ParentRegistrationForm(
                    {
                        "family_name": family_name,
                        "display_name": "Morgan",
                        "password1": "different-test-pass-123",
                        "password2": "different-test-pass-123",
                    },
                    invitation=FamilyInvitation.objects.get(pk=invitation.pk),
                )
                if not form.is_valid():
                    raise AssertionError(form.errors)
                barrier.wait(timeout=10)
                try:
                    form.save()
                    return "created"
                except ValidationError:
                    return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(register, ["Willow", "Oak"]))
        self.assertCountEqual(results, ["created", "rejected"])
        self.assertEqual(Family.objects.count(), 2)
        self.assertEqual(User.objects.filter(email="new@example.com").count(), 1)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "accepted")
        self.assertIsNotNone(invitation.accepted_family_id)
