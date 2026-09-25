from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from directory.models import (
    Child,
    ChildConnection,
    ConnectionInvitation,
    Family,
    Parent,
)
from directory.tests.factories import create_user


@override_settings(
    FRONTPORCH_PUBLIC_URL="https://parents.example.com/",
    DEFAULT_FROM_EMAIL="FrontPorch <noreply@example.com>",
)
class ConnectionNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = Family.objects.create(name="Maple", directory_listed=True)
        cls.target = Family.objects.create(name="Willow", directory_listed=True)
        cls.sender = Parent.objects.create(
            family=cls.source,
            user=create_user(email="sender@example.com"),
            display_name="Taylor",
        )
        cls.primary = Parent.objects.create(
            family=cls.target,
            user=create_user(email="primary@example.com"),
            display_name="Morgan",
            is_primary=True,
        )
        cls.secondary = Parent.objects.create(
            family=cls.target,
            user=create_user(email="secondary@example.com"),
            display_name="Sam",
        )
        cls.child = Child.objects.create(family=cls.source, name="Private child name")
        cls.peer = Child.objects.create(family=cls.target, name="Other private child")

    def setUp(self):
        self.client.force_login(self.sender.user)

    def post_request(self, family=None, child=None):
        url = reverse("directory:connection_invite")
        return self.client.post(
            url + f"?family={(family or self.target).pk}",
            {
                "children": [(child or self.child).pk],
                "message": "Private message for the receiving family.",
            },
        )

    def test_alerts_send_only_after_commit_separately_without_private_details(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_request()
            self.assertEqual(response.status_code, 302)
            self.assertEqual(mail.outbox, [])

        invitation = ConnectionInvitation.objects.get()
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            [message.to for message in mail.outbox],
            [["primary@example.com"], ["secondary@example.com"]],
        )
        url = "https://parents.example.com" + reverse(
            "directory:connection_review", args=[invitation.pk]
        )
        for message in mail.outbox:
            self.assertEqual(message.from_email, "FrontPorch <noreply@example.com>")
            self.assertIn(url, message.body)
            self.assertEqual(message.cc, [])
            self.assertEqual(message.bcc, [])
            for private in (
                self.child.name,
                self.peer.name,
                invitation.message,
                self.source.invite_code,
                "primary@example.com",
                "secondary@example.com",
            ):
                self.assertNotIn(private, message.body)
                self.assertNotIn(private, message.subject)
        self.assertEqual(invitation.status, "pending")
        self.assertFalse(ChildConnection.objects.exists())

    def test_recipients_are_current_active_guardians_with_distinct_email_addresses(self):
        for name, email, guardian, active in (
            ("Former", "former@example.com", False, True),
            ("Inactive", "inactive@example.com", True, False),
            ("No email", "", True, True),
            ("Duplicate", "PRIMARY@example.com", True, True),
        ):
            Parent.objects.create(
                family=self.target,
                display_name=name,
                user=create_user(email=email, is_active=active),
                is_guardian=guardian,
            )
        with self.captureOnCommitCallbacks(execute=True):
            self.post_request()
        self.assertEqual(
            [message.to for message in mail.outbox],
            [["primary@example.com"], ["secondary@example.com"]],
        )

    def test_recipient_access_is_rechecked_after_commit(self):
        with self.captureOnCommitCallbacks() as callbacks:
            self.post_request()
        Parent.objects.filter(pk=self.primary.pk).update(is_guardian=False)
        self.secondary.user.is_active = False
        self.secondary.user.save(update_fields=["is_active"])
        for callback in callbacks:
            callback()
        self.assertEqual(mail.outbox, [])
        self.assertTrue(ConnectionInvitation.objects.filter(status="pending").exists())

    def test_closed_or_revoked_sender_requests_do_not_send_delayed_alerts(self):
        with self.captureOnCommitCallbacks() as callbacks:
            self.post_request()
        invitation = ConnectionInvitation.objects.get()
        for status in ("cancelled", "declined", "accepted"):
            with self.subTest(status=status):
                ConnectionInvitation.objects.filter(pk=invitation.pk).update(
                    status=status
                )
                for callback in callbacks:
                    callback()
                self.assertEqual(mail.outbox, [])
        ConnectionInvitation.objects.filter(pk=invitation.pk).update(status="pending")
        Parent.objects.filter(pk=self.sender.pk).update(is_guardian=False)
        for callback in callbacks:
            callback()
        self.assertEqual(mail.outbox, [])

    def test_rollback_does_not_send_alerts(self):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    self.post_request()
                    raise RuntimeError("Abort the request transaction")
        self.assertFalse(ConnectionInvitation.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_duplicate_in_either_direction_does_not_send_again(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.post_request()
            self.assertEqual(self.post_request().status_code, 200)
            self.client.force_login(self.primary.user)
            self.assertEqual(
                self.post_request(family=self.source, child=self.peer).status_code, 200
            )
        self.assertEqual(ConnectionInvitation.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_invalid_and_unauthorized_requests_send_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.post_request(child=self.peer).status_code, 200)
            self.target.directory_listed = False
            self.target.save()
            self.assertEqual(self.post_request().status_code, 404)
            Parent.objects.filter(pk=self.sender.pk).update(is_guardian=False)
            self.assertEqual(self.post_request().status_code, 403)
            self.client.logout()
            self.assertEqual(self.post_request().status_code, 302)
        self.assertEqual(mail.outbox, [])
        self.assertFalse(ConnectionInvitation.objects.exists())

    def test_email_link_requires_login_and_receiving_family_membership(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.post_request()
        path = reverse(
            "directory:connection_review", args=[ConnectionInvitation.objects.get().pk]
        )
        self.assertEqual(self.client.get(path).status_code, 404)
        self.client.logout()
        self.assertRedirects(
            self.client.get(path),
            "/accounts/login/?next=" + path,
            fetch_redirect_response=False,
        )
        self.client.force_login(self.primary.user)
        self.assertEqual(self.client.get(path).status_code, 200)
        Parent.objects.filter(pk=self.primary.pk).update(is_guardian=False)
        self.assertEqual(self.client.get(path).status_code, 403)
        self.assertFalse(ChildConnection.objects.exists())

    @override_settings(FRONTPORCH_PUBLIC_URL="")
    def test_request_origin_is_used_when_no_canonical_origin_is_configured(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.post_request()
        path = reverse(
            "directory:connection_review", args=[ConnectionInvitation.objects.get().pk]
        )
        self.assertIn("http://testserver" + path, mail.outbox[0].body)

    def test_failed_email_preserves_request_and_attempts_other_guardians(self):
        real_send = mail.send_mail

        def fail_first(*args, **kwargs):
            if args[3] == ["primary@example.com"]:
                raise SMTPException("Sensitive provider response primary@example.com")
            return real_send(*args, **kwargs)

        with patch("directory.notifications.send_mail", side_effect=fail_first):
            with self.assertLogs("directory.notifications", level="WARNING") as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.post_request()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ConnectionInvitation.objects.filter(status="pending").exists())
        self.assertEqual(
            [message.to for message in mail.outbox], [["secondary@example.com"]]
        )
        self.assertNotIn("primary@example.com", "".join(logs.output))
        self.assertNotIn("Sensitive provider response", "".join(logs.output))
        self.assertFalse(ChildConnection.objects.exists())

    def test_transport_error_and_zero_send_result_preserve_request(self):
        for outcome in (OSError("offline"), 0):
            with self.subTest(outcome=type(outcome).__name__):
                ConnectionInvitation.objects.all().delete()
                with (
                    patch(
                        "directory.notifications.send_mail",
                        side_effect=[outcome, outcome],
                    ),
                    self.assertLogs("directory.notifications", level="WARNING") as logs,
                    self.captureOnCommitCallbacks(execute=True),
                ):
                    response = self.post_request()
                self.assertEqual(response.status_code, 302)
                self.assertEqual(len(logs.output), 2)
                self.assertTrue(
                    ConnectionInvitation.objects.filter(status="pending").exists()
                )
                self.assertEqual(mail.outbox, [])
