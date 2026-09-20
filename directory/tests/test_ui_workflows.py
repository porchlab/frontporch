from directory.tests.factories import create_user
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from directory import models as m
from directory.asterisk.builder import build_asterisk_configuration


class ParentUIWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.family = m.Family.objects.create(name="Maple", directory_listed=True)
        cls.remote = m.Family.objects.create(name="Willow", directory_listed=True)
        cls.hidden = m.Family.objects.create(name="Hidden household")
        cls.user = User.objects.create_user(
            "maple", "maple@example.com", "test-pass-12"
        )
        cls.other_user = User.objects.create_user(
            "willow", "willow@example.com", "test-pass-12"
        )
        cls.parent = m.Parent.objects.create(
            family=cls.family,
            user=cls.user,
            display_name="Taylor",
            directory_visible=True,
        )
        cls.other = m.Parent.objects.create(
            family=cls.remote,
            user=cls.other_user,
            display_name="Morgan",
            directory_visible=True,
        )
        cls.hidden_parent = m.Parent.objects.create(
            user=create_user(email="private@example.com"),
            family=cls.hidden,
            display_name="Secret guardian",
        )
        cls.child = m.Child.objects.create(family=cls.family, name="Casey")
        cls.sibling = m.Child.objects.create(family=cls.family, name="Riley")
        cls.peer = m.Child.objects.create(family=cls.remote, name="Alex")
        cls.excluded = m.Child.objects.create(family=cls.remote, name="Jamie")
        cls.device = m.Device.objects.create(
            assigned_child=cls.child,
            friendly_name="Bedroom",
            sip_extension="5201",
            sip_username="casey-phone",
            sip_secret="fictional-secret",
        )
        cls.peer_device = m.Device.objects.create(
            assigned_child=cls.peer,
            friendly_name="Remote bedroom",
            sip_extension="5202",
            sip_username="alex-phone",
            sip_secret="other-fictional-secret",
        )
        cls.excluded_device = m.Device.objects.create(
            assigned_child=cls.excluded,
            friendly_name="Remote sibling",
            sip_extension="5203",
            sip_username="jamie-phone",
            sip_secret="excluded-secret",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_all_pages_render_and_hide_phone_credentials(self):
        routes = [
            "dashboard",
            "children",
            "contacts",
            "family_directory",
            "connections",
            "invitations",
            "settings",
            "welcome",
        ]
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(reverse("directory:" + route))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, self.device.sip_secret)
                self.assertNotContains(response, self.peer_device.sip_secret)
        for route, args in [
            ("child_detail", [self.child.pk]),
            ("shortcuts", [self.device.pk]),
            ("shortcut_create", [self.device.pk]),
        ]:
            self.assertEqual(
                self.client.get(reverse("directory:" + route, args=args)).status_code,
                200,
            )

    def test_directory_is_opt_in_and_does_not_expose_private_data(self):
        response = self.client.get(reverse("directory:family_directory"))
        for private in [
            self.hidden.name,
            self.hidden_parent.display_name,
            self.hidden_parent.email,
            self.hidden.invite_code,
            self.peer.name,
            self.excluded.name,
            self.peer_device.sip_extension,
        ]:
            self.assertNotContains(response, private)
        self.assertContains(response, "Morgan")
        self.assertEqual(
            self.client.get(reverse("directory:family_directory"), {"q": "Secret"})
            .context["page"]
            .paginator.count,
            0,
        )
        response = self.client.get(
            reverse("directory:connection_invite"), {"family": self.hidden.pk}
        )
        self.assertEqual(response.status_code, 404)

    def test_family_code_lookup_and_rotation(self):
        response = self.client.post(
            reverse("directory:invite_code"), {"code": self.hidden.invite_code}
        )
        self.assertEqual(response.status_code, 302)
        url = reverse("directory:connection_invite") + f"?family={self.hidden.pk}"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.hidden.invite_code = m.new_family_invite_code()
        self.hidden.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(m.ChildConnection.objects.count(), 0)

    def send_invitation(self):
        response = self.client.post(
            reverse("directory:connection_invite") + f"?family={self.remote.pk}",
            {"children": [self.child.pk], "message": "Hello!"},
        )
        self.assertEqual(response.status_code, 302)
        return m.ConnectionInvitation.objects.get()

    def test_acceptance_creates_only_selected_pairs_and_revocation_removes_routes(self):
        invitation = self.send_invitation()
        self.assertFalse(m.ChildConnection.objects.exists())
        self.client.force_login(self.other_user)
        response = self.client.post(
            reverse("directory:connection_review", args=[invitation.pk]),
            {"children": [self.peer.pk]},
        )
        self.assertEqual(response.status_code, 302)
        pair = m.ChildConnection.objects.get()
        self.assertEqual(
            {pair.child_a_id, pair.child_b_id}, {self.child.pk, self.peer.pk}
        )
        config = build_asterisk_configuration()
        routes = {
            (r.source_endpoint.extension, r.target_endpoint.extension)
            for r in config.dialplan_rules
        }
        self.assertIn(("5201", "5202"), routes)
        self.assertIn(("5202", "5201"), routes)
        self.assertNotIn(("5201", "5203"), routes)
        self.client.post(
            reverse("directory:connection_review", args=[invitation.pk]),
            {"children": [self.excluded.pk]},
        )
        self.assertEqual(m.ChildConnection.objects.count(), 1)
        self.client.force_login(self.user)
        self.client.post(
            reverse("directory:shortcut_create", args=[self.device.pk]),
            {
                "digits": "1",
                "target": f"device:{self.peer_device.pk}",
                "is_active": "on",
            },
        )
        self.assertEqual(len(build_asterisk_configuration().shortcut_rules), 1)
        self.client.post(reverse("directory:connection_remove", args=[pair.pk]))
        self.assertEqual(build_asterisk_configuration().shortcut_rules, ())
        self.assertEqual(m.DialShortcut.objects.count(), 1)
        self.assertContains(
            self.client.get(reverse("directory:shortcuts", args=[self.device.pk])),
            "Unavailable",
        )
        shortcut = m.DialShortcut.objects.get()
        self.client.post(
            reverse("directory:shortcut_action", args=[shortcut.pk, "pause"])
        )
        shortcut.refresh_from_db()
        self.assertFalse(shortcut.is_active)

    def test_invitation_cannot_include_other_family_children_or_accept_for_wrong_family(
        self,
    ):
        url = reverse("directory:connection_invite") + f"?family={self.remote.pk}"
        response = self.client.post(url, {"children": [self.peer.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(m.ConnectionInvitation.objects.exists())
        invitation = self.send_invitation()
        self.assertEqual(
            self.client.post(
                reverse("directory:connection_review", args=[invitation.pk]),
                {"children": [self.child.pk]},
            ).status_code,
            404,
        )
        self.client.force_login(self.other_user)
        self.client.post(
            reverse("directory:connection_review", args=[invitation.pk]),
            {"children": [self.child.pk]},
        )
        self.assertFalse(m.ChildConnection.objects.exists())

    def test_cancellation_and_decline_never_grant_access(self):
        invitation = self.send_invitation()
        self.client.post(
            reverse("directory:invitation_action", args=[invitation.pk, "cancel"])
        )
        self.client.force_login(self.other_user)
        self.client.post(
            reverse("directory:connection_review", args=[invitation.pk]),
            {"children": [self.peer.pk]},
        )
        self.assertFalse(m.ChildConnection.objects.exists())
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "cancelled")

    def test_phone_reservation_is_inactive_and_ignores_submitted_credentials(self):
        response = self.client.post(
            reverse("directory:phone_create", args=[self.child.pk]),
            {
                "friendly_name": "Kitchen phone",
                "is_active": "on",
                "sip_extension": "5202",
                "sip_secret": "attacker",
            },
        )
        self.assertEqual(response.status_code, 302)
        device = m.Device.objects.get(friendly_name="Kitchen phone")
        self.assertFalse(device.is_active)
        self.assertNotEqual(device.sip_extension, "5202")
        self.assertEqual(len(device.sip_extension), 4)
        self.assertNotEqual(device.sip_secret, "attacker")
        self.assertNotIn(
            device.pk, [d.device_id for d in build_asterisk_configuration().endpoints]
        )

    def test_contact_validation_and_revocation_of_shortcuts(self):
        url = reverse("directory:contact_create")
        self.assertContains(
            self.client.post(url, {"label": "Grandparent", "phone_number": "invalid"}),
            "Enter a valid phone number.",
        )
        self.client.post(url, {"label": "Grandparent", "phone_number": "202-555-0198"})
        contact = m.FamilyContact.objects.get(family=self.family)
        self.assertContains(
            self.client.post(
                url, {"label": "Duplicate", "phone_number": "+12025550198"}
            ),
            "already saved",
        )
        self.client.post(
            reverse("directory:shortcut_create", args=[self.device.pk]),
            {
                "digits": "1",
                "target": f"external:{contact.dial_extension.pk}",
                "is_active": "on",
            },
        )
        self.assertEqual(len(build_asterisk_configuration().shortcut_rules), 1)
        self.client.post(reverse("directory:contact_delete", args=[contact.pk]))
        self.assertEqual(build_asterisk_configuration().shortcut_rules, ())

    def test_ownership_guardian_role_and_csrf_are_enforced(self):
        self.assertEqual(
            self.client.get(
                reverse("directory:child_detail", args=[self.peer.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("directory:shortcuts", args=[self.peer_device.pk])
            ).status_code,
            404,
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(
            csrf_client.post(
                reverse("directory:phone_create", args=[self.child.pk]),
                {"friendly_name": "Phone"},
            ).status_code,
            403,
        )
        self.parent.is_guardian = False
        self.parent.save()
        self.assertEqual(
            self.client.get(reverse("directory:dashboard")).status_code, 403
        )

    def test_shortcuts_reject_unapproved_target_and_duplicate_digit(self):
        url = reverse("directory:shortcut_create", args=[self.device.pk])
        self.client.post(
            url,
            {
                "digits": "1",
                "target": f"device:{self.peer_device.pk}",
                "is_active": "on",
            },
        )
        self.assertFalse(m.DialShortcut.objects.exists())
        self.client.post(
            url,
            {"digits": "0", "target": f"device:{self.device.pk}", "is_active": "on"},
        )
        self.assertFalse(m.DialShortcut.objects.exists())

    def test_preferences_do_not_change_permissions_and_are_family_scoped(self):
        self.client.post(
            reverse("directory:settings"),
            {"form": "family", "name": "Maple renamed", "directory_listed": "on"},
        )
        self.family.refresh_from_db()
        self.assertTrue(self.family.directory_listed)
        self.assertFalse(m.ChildConnection.objects.exists())
        self.client.post(
            reverse("directory:preference", args=["setup"]), {"dismissed": "true"}
        )
        self.assertNotContains(
            self.client.get(reverse("directory:dashboard")), "Family setup checklist"
        )
        self.assertTrue(m.FamilyActivity.objects.filter(family=self.family).exists())
        self.assertFalse(m.FamilyActivity.objects.filter(family=self.remote).exists())

    def test_user_text_is_escaped_and_phone_rename_cannot_activate(self):
        self.child.name = "<img src=x onerror=alert(1)>"
        self.child.save()
        response = self.client.get(reverse("directory:children"))
        self.assertNotContains(response, "<img src=x")
        self.assertContains(response, "&lt;img src=x")
        self.device.is_active = False
        self.device.save()
        self.client.post(
            reverse("directory:phone_edit", args=[self.device.pk]),
            {
                "friendly_name": "Renamed phone",
                "is_active": "on",
                "sip_extension": "9999",
            },
        )
        self.device.refresh_from_db()
        self.assertEqual(self.device.friendly_name, "Renamed phone")
        self.assertEqual(self.device.sip_extension, "5201")
        self.assertFalse(self.device.is_active)

    def test_duplicate_child_and_guardian_names_return_form_errors(self):
        response = self.client.post(
            reverse("directory:child_create"), {"name": self.child.name.lower()}
        )
        self.assertContains(response, "A child with this name already belongs")
        self.assertEqual(self.family.children.count(), 2)
        m.Parent.objects.create(
            user=create_user(),
            family=self.family,
            display_name="Second guardian",
        )
        response = self.client.post(
            reverse("directory:settings"),
            {"form": "profile", "display_name": "second GUARDIAN"},
        )
        self.assertContains(response, "A guardian with this name already belongs")
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.display_name, "Taylor")
