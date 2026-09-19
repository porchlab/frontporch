import re
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from directory.models import Family, Parent, GuardianInvitation, Child, FamilyActivity


class GuardianInvitationTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Maple")
        self.user = User.objects.create_user(
            "primary", "primary@example.com", "test-password-123"
        )
        self.parent = Parent.objects.create(
            user=self.user,
            family=self.family,
            display_name="Taylor",
            email=self.user.email,
            is_primary=True,
        )
        self.child = Child.objects.create(family=self.family, name="Casey")
        self.client.force_login(self.user)

    def invite(self, email="guardian@example.com"):
        response = self.client.post(
            reverse("directory:guardian_invite"),
            {"display_name": "Morgan", "email": email},
        )
        self.assertRedirects(response, reverse("directory:settings"))
        invitation = GuardianInvitation.objects.order_by("-pk").first()
        token = re.search(r"/guardians/join/([^/]+)/", mail.outbox[-1].body).group(1)
        return invitation, token

    def test_invitation_is_pending_email_bound_and_does_not_grant_access(self):
        invitation, token = self.invite()
        self.assertEqual(Parent.objects.filter(family=self.family).count(), 1)
        self.assertEqual(mail.outbox[-1].to, ["guardian@example.com"])
        self.assertNotEqual(invitation.token_digest, token)
        self.assertNotContains(self.client.get(reverse("directory:settings")), token)
        self.assertEqual(self.family.children.get(), self.child)

    def test_new_account_joins_existing_household_and_token_is_single_use(self):
        invitation, token = self.invite()
        self.client.logout()
        response = self.client.post(
            reverse("directory:guardian_join", args=[token]),
            {
                "password1": "different-test-pass-123",
                "password2": "different-test-pass-123",
            },
        )
        self.assertRedirects(response, reverse("directory:dashboard"))
        joined = Parent.objects.get(email="guardian@example.com")
        self.assertEqual(joined.family, self.family)
        self.assertFalse(joined.is_primary)
        self.assertFalse(joined.directory_visible)
        self.assertEqual(Family.objects.count(), 1)
        self.assertEqual(self.family.children.get(), self.child)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "accepted")
        self.assertEqual(
            self.client.post(
                reverse("directory:guardian_join", args=[token])
            ).status_code,
            410,
        )
        self.assertTrue(
            FamilyActivity.objects.filter(description__contains="joined").exists()
        )

    def test_existing_account_must_log_in_with_invited_email(self):
        recipient = User.objects.create_user(
            "recipient", "guardian@example.com", "test-password-123"
        )
        invitation, token = self.invite()
        url = reverse("directory:guardian_join", args=[token])
        self.client.logout()
        response = self.client.post(
            url,
            {
                "username": "fake",
                "password1": "different-test-pass-123",
                "password2": "different-test-pass-123",
            },
        )
        self.assertContains(response, "already has an account")
        self.assertFalse(User.objects.filter(username="fake").exists())
        self.client.force_login(self.user)
        self.assertContains(self.client.post(url), "email matches")
        self.client.force_login(recipient)
        self.assertRedirects(self.client.post(url), reverse("directory:dashboard"))
        self.assertEqual(recipient.frontporch_parent.family, self.family)

    def test_existing_member_of_another_family_is_never_moved(self):
        recipient = User.objects.create_user(
            "recipient", "guardian@example.com", "test-password-123"
        )
        invitation, token = self.invite()
        other = Family.objects.create(name="Willow")
        member = Parent.objects.create(
            user=recipient, family=other, display_name="Morgan", email=recipient.email
        )
        self.client.force_login(recipient)
        self.assertContains(
            self.client.post(reverse("directory:guardian_join", args=[token])),
            "cannot be moved",
        )
        member.refresh_from_db()
        self.assertEqual(member.family, other)

    def test_cancel_expiry_and_replacement_invalidate_links(self):
        invitation, token = self.invite()
        self.client.post(
            reverse(
                "directory:guardian_invitation_action", args=[invitation.pk, "resend"]
            )
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "replaced")
        self.assertEqual(
            self.client.get(
                reverse("directory:guardian_join", args=[token])
            ).status_code,
            410,
        )
        replacement = GuardianInvitation.objects.get(status="pending")
        second_token = re.search(
            r"/guardians/join/([^/]+)/", mail.outbox[-1].body
        ).group(1)
        replacement.expires_at = timezone.now() - timedelta(seconds=1)
        replacement.save()
        self.assertEqual(
            self.client.get(
                reverse("directory:guardian_join", args=[second_token])
            ).status_code,
            410,
        )
        self.client.post(
            reverse(
                "directory:guardian_invitation_action", args=[replacement.pk, "cancel"]
            )
        )
        replacement.refresh_from_db()
        self.assertEqual(replacement.status, "cancelled")

    def test_email_failure_does_not_claim_success_or_replace_valid_invitation(self):
        with patch("directory.guardians.send_mail", side_effect=OSError("offline")):
            response = self.client.post(
                reverse("directory:guardian_invite"),
                {"display_name": "Morgan", "email": "guardian@example.com"},
            )
        self.assertContains(response, "could not be emailed")
        self.assertFalse(GuardianInvitation.objects.exists())
        invitation, token = self.invite()
        with patch("directory.guardians.send_mail", side_effect=OSError("offline")):
            self.client.post(
                reverse(
                    "directory:guardian_invitation_action",
                    args=[invitation.pk, "resend"],
                )
            )
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "pending")
        self.assertEqual(GuardianInvitation.objects.count(), 1)

    def test_only_primary_guardian_can_manage_membership(self):
        user = User.objects.create_user(
            "added", "added@example.com", "test-password-123"
        )
        added = Parent.objects.create(
            user=user, family=self.family, display_name="Added"
        )
        invitation, token = self.invite()
        self.client.force_login(user)
        self.assertEqual(
            self.client.get(reverse("directory:guardian_invite")).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                reverse(
                    "directory:guardian_invitation_action",
                    args=[invitation.pk, "cancel"],
                )
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("directory:guardian_remove", args=[self.parent.pk])
            ).status_code,
            403,
        )
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.post(
                reverse("directory:guardian_remove", args=[self.parent.pk])
            ).status_code,
            404,
        )
        self.client.post(reverse("directory:guardian_remove", args=[added.pk]))
        self.client.force_login(user)
        self.assertEqual(
            self.client.get(reverse("directory:dashboard")).status_code, 403
        )
        self.assertEqual(self.family.children.get(), self.child)

    def test_signup_and_login_with_email_without_a_username(self):
        self.client.logout()
        response = self.client.post(
            reverse("directory:register"),
            {
                "email": "new@example.com",
                "family_name": "Oak",
                "display_name": "Rowan",
                "password1": "different-test-pass-123",
                "password2": "different-test-pass-123",
                "directory_listed": "on",
            },
        )
        self.assertRedirects(response, reverse("directory:dashboard"))
        parent = Parent.objects.get(email="new@example.com")
        self.assertTrue(parent.is_primary)
        self.assertTrue(parent.family.directory_listed)
        self.assertTrue(parent.directory_visible)
        self.client.logout()
        self.assertRedirects(
            self.client.post(
                reverse("login"),
                {"username": "NEW@example.com", "password": "different-test-pass-123"},
            ),
            reverse("directory:dashboard"),
        )

    def test_removed_guardian_can_rejoin_only_the_same_family_with_new_invitation(self):
        recipient = User.objects.create_user(
            "returning", "guardian@example.com", "test-password-123"
        )
        member = Parent.objects.create(
            user=recipient,
            family=self.family,
            display_name="Morgan",
            email=recipient.email,
            is_guardian=False,
        )
        invitation, token = self.invite()
        self.client.force_login(recipient)
        self.assertRedirects(
            self.client.post(reverse("directory:guardian_join", args=[token])),
            reverse("directory:dashboard"),
        )
        member.refresh_from_db()
        self.assertTrue(member.is_guardian)
        self.assertEqual(Parent.objects.filter(user=recipient).count(), 1)
