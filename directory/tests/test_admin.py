from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from directory.models import (
    Child,
    ChildLandline,
    ChildLandlineDialShortcut,
    Device,
    DialShortcut,
    ExternalPhoneNumber,
    Family,
    Parent,
)


class DirectoryAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="secret-pass",
        )
        self.family = Family.objects.create(name="River House")
        self.child = Child.objects.create(family=self.family, name="Alex")
        self.target_child = Child.objects.create(family=self.family, name="Rowan")
        self.parent = Parent.objects.create(family=self.family, display_name="Mara")
        self.source_device = Device.objects.create(
            assigned_parent=self.parent,
            friendly_name="Mara kitchen phone",
            sip_extension="201",
            sip_username="mara-201",
            sip_secret="secret-m",
        )
        Device.objects.create(
            assigned_child=self.target_child,
            friendly_name="Rowan bedroom phone",
            sip_extension="3552",
            sip_username="rowan-3552",
            sip_secret="secret-rowan",
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 212 555 0100"
        )
        self.landline = ChildLandline.objects.create(
            child=self.child,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.parent,
        )
        self.client.force_login(self.admin_user)

    def test_admin_can_set_child_spoken_name_without_changing_display_name(self):
        response = self.client.post(
            reverse("admin:directory_child_change", args=[self.target_child.id]),
            {
                "family": self.family.id,
                "name": "Rowan",
                "spoken_name": "ROH-wan",
                "notes": "",
                "_save": "Save",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.target_child.refresh_from_db()
        self.assertEqual(self.target_child.name, "Rowan")
        self.assertEqual(self.target_child.spoken_name, "ROH-wan")

    def test_admin_can_create_dial_shortcut_to_child_landline(self):
        self.assert_admin_can_create_dial_shortcut("_save")

    def test_admin_can_create_dial_shortcut_to_child_landline_and_continue(self):
        self.assert_admin_can_create_dial_shortcut("_continue")

    def test_admin_can_create_dial_shortcut_to_child_landline_and_add_another(self):
        self.assert_admin_can_create_dial_shortcut("_addanother")

    def test_admin_can_create_child_landline_dial_shortcut(self):
        response = self.client.post(
            reverse("admin:directory_childlandlinedialshortcut_add"),
            {
                "source_landline": self.landline.id,
                "digits": "2",
                "target_child": self.target_child.id,
                "approved_by": self.parent.id,
                "label": "Rowan",
                "is_active": "on",
                "notes": "",
                "_save": "Save",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        shortcut = ChildLandlineDialShortcut.objects.get(
            source_landline=self.landline,
            digits="2",
        )
        self.assertEqual(shortcut.target_child, self.target_child)

    def assert_admin_can_create_dial_shortcut(self, submit_name):
        response = self.client.post(
            reverse("admin:directory_dialshortcut_add"),
            {
                "source_device": self.source_device.id,
                "digits": "2",
                "internal_target_device": "",
                "external_target_extension": "",
                "parent_phone_target": "",
                "child_landline_target": self.landline.id,
                "label": "Alex landline",
                "approved_by": self.parent.id,
                "is_active": "on",
                "notes": "",
                submit_name: "Save",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        shortcut = DialShortcut.objects.get(source_device=self.source_device, digits="2")
        self.assertEqual(shortcut.child_landline_target, self.landline)
