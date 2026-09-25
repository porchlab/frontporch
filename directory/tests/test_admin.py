from directory.tests.factories import create_user
from django.contrib.admin.models import DELETION, LogEntry
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from directory.models import (
    Child,
    ChildLandline,
    ChildLandlineDialShortcut,
    ConferenceGroup,
    Device,
    DialShortcut,
    ExternalPhoneNumber,
    Family,
    FamilyActivity,
    Parent,
)


class FamilyDeletionAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="secret-pass"
        )
        cls.family = Family.objects.create(name="River House")
        cls.child = Child.objects.create(family=cls.family, name="Alex")
        cls.activity = FamilyActivity.objects.create(
            family=cls.family, description="Added Alex."
        )
        cls.other_family = Family.objects.create(name="Willow House")
        cls.other_activity = FamilyActivity.objects.create(
            family=cls.other_family, description="Created family."
        )

    def setUp(self):
        self.client.force_login(self.admin_user)
        self.delete_url = reverse("admin:directory_family_delete", args=[self.family.pk])
        self.changelist_url = reverse("admin:directory_family_changelist")

    def login_staff(self, *permissions):
        staff = create_user(is_staff=True)
        staff.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="directory", codename__in=permissions
            )
        )
        self.client.force_login(staff)
        return staff

    def assert_family_deleted(self, family, actor):
        self.assertFalse(Family.objects.filter(pk=family.pk).exists())
        self.assertFalse(Child.objects.filter(family_id=family.pk).exists())
        self.assertFalse(FamilyActivity.objects.filter(family_id=family.pk).exists())
        self.assertTrue(
            LogEntry.objects.filter(
                user=actor,
                content_type__app_label="directory",
                content_type__model="family",
                object_id=str(family.pk),
                action_flag=DELETION,
            ).exists()
        )

    def test_superuser_can_delete_family_with_activity(self):
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["perms_lacking"])
        self.assertFalse(response.context["protected"])
        self.assertContains(response, "Family activity")
        self.assertTrue(Family.objects.filter(pk=self.family.pk).exists())

        response = self.client.post(self.delete_url, {"post": "yes"})

        self.assertRedirects(response, self.changelist_url)
        self.assert_family_deleted(self.family, self.admin_user)
        self.assertTrue(Family.objects.filter(pk=self.other_family.pk).exists())
        self.assertTrue(FamilyActivity.objects.filter(pk=self.other_activity.pk).exists())

    def test_bulk_family_deletion_includes_activity(self):
        data = {
            "action": "delete_selected",
            "_selected_action": [self.family.pk, self.other_family.pk],
        }
        response = self.client.post(self.changelist_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["perms_lacking"])
        self.assertContains(response, "Family activity")
        self.assertEqual(Family.objects.count(), 2)

        response = self.client.post(self.changelist_url, {**data, "post": "yes"})

        self.assertRedirects(response, self.changelist_url)
        self.assert_family_deleted(self.family, self.admin_user)
        self.assert_family_deleted(self.other_family, self.admin_user)

    def test_staff_can_delete_family_without_activity_delete_permission(self):
        staff = self.login_staff("view_family", "delete_family", "delete_child")
        self.assertFalse(staff.has_perm("directory.delete_familyactivity"))

        response = self.client.post(self.delete_url, {"post": "yes"})

        self.assertRedirects(response, reverse("admin:index"))
        self.assert_family_deleted(self.family, staff)

    def test_family_delete_permission_is_still_required(self):
        self.login_staff("view_family", "delete_child", "delete_familyactivity")

        response = self.client.post(self.delete_url, {"post": "yes"})

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Family.objects.filter(pk=self.family.pk).exists())
        self.assertTrue(FamilyActivity.objects.filter(pk=self.activity.pk).exists())

    def test_other_cascade_delete_permissions_are_still_required(self):
        self.login_staff("view_family", "delete_family")

        response = self.client.get(self.delete_url)
        self.assertEqual(response.context["perms_lacking"], {"child"})
        response = self.client.post(self.delete_url, {"post": "yes"})

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Family.objects.filter(pk=self.family.pk).exists())
        self.assertTrue(Child.objects.filter(pk=self.child.pk).exists())
        self.assertTrue(FamilyActivity.objects.filter(pk=self.activity.pk).exists())

    def test_protected_device_still_blocks_family_deletion(self):
        device = Device.objects.create(
            assigned_family=self.family,
            friendly_name="Kitchen phone",
            sip_extension="3552",
            sip_username="river-kitchen",
            sip_secret="test-secret",
        )

        response = self.client.post(self.delete_url, {"post": "yes"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["protected"])
        self.assertTrue(Family.objects.filter(pk=self.family.pk).exists())
        self.assertTrue(Device.objects.filter(pk=device.pk).exists())
        self.assertTrue(FamilyActivity.objects.filter(pk=self.activity.pk).exists())

    def test_superuser_cannot_delete_activity_directly_or_in_bulk(self):
        url = reverse("admin:directory_familyactivity_delete", args=[self.activity.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)

        url = reverse("admin:directory_familyactivity_changelist")
        response = self.client.get(url)
        self.assertIsNone(response.context["action_form"])
        self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [self.activity.pk],
                "post": "yes",
            },
        )
        self.assertTrue(FamilyActivity.objects.filter(pk=self.activity.pk).exists())


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
        self.parent = Parent.objects.create(
            user=create_user(),
            family=self.family,
            display_name="Mara",
            dial_extension="201",
        )
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

    def test_admin_lists_child_connections_without_retired_family_relationships(self):
        response = self.client.get(reverse("admin:index"))

        self.assertContains(response, "Child connections")
        self.assertNotContains(response, "Allowed child family relationships")
        self.assertEqual(
            self.client.get("/admin/directory/allowedchildfamilyrelationship/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("admin:directory_childconnection_changelist")
            ).status_code,
            200,
        )

    def test_activity_archive_details_are_visible_but_read_only_for_staff(self):
        activity = FamilyActivity.objects.create(
            family=self.family,
            description="Archived retired approval (history only).",
            details={"notes": "Historical staff-only approval note."},
        )
        url = reverse("admin:directory_familyactivity_change", args=[activity.pk])
        self.assertContains(self.client.get(url), "Historical staff-only approval note.")
        response = self.client.post(url, {"details": "{}", "_save": "Save"})
        self.assertEqual(response.status_code, 403)
        activity.refresh_from_db()
        self.assertEqual(activity.details["notes"], "Historical staff-only approval note.")

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

    def test_admin_can_enable_conference_calling_with_auto_extension(self):
        response = self.client.post(
            reverse("admin:directory_conferencegroup_add"),
            {
                "name": "Friends",
                "members": [self.child.id, self.target_child.id],
                "approved_by": self.parent.id,
                "is_active": "on",
                "calling_enabled": "on",
                "dial_extension": "",
                "ring_timeout_seconds": "25",
                "notes": "",
                "_save": "Save",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        group = ConferenceGroup.objects.get(name="Friends")
        self.assertTrue(group.calling_enabled)
        self.assertEqual(len(group.dial_extension), 4)
        self.assertEqual(group.ring_timeout_seconds, 25)

    def test_admin_can_create_dial_shortcut_to_conference_group(self):
        child_device = Device.objects.create(
            assigned_child=self.child,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-alex",
        )
        group = ConferenceGroup.objects.create(
            name="Friends",
            approved_by=self.parent,
            calling_enabled=True,
            dial_extension="4444",
        )
        group.members.set([self.child, self.target_child])

        response = self.client.post(
            reverse("admin:directory_dialshortcut_add"),
            {
                "source_device": child_device.id,
                "digits": "3",
                "internal_target_device": "",
                "external_target_extension": "",
                "parent_target": "",
                "child_landline_target": "",
                "conference_group_target": group.id,
                "label": "Friends",
                "approved_by": self.parent.id,
                "is_active": "on",
                "notes": "",
                "_save": "Save",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        shortcut = DialShortcut.objects.get(source_device=child_device, digits="3")
        self.assertEqual(shortcut.conference_group_target, group)

    def assert_admin_can_create_dial_shortcut(self, submit_name):
        response = self.client.post(
            reverse("admin:directory_dialshortcut_add"),
            {
                "source_device": self.source_device.id,
                "digits": "2",
                "internal_target_device": "",
                "external_target_extension": "",
                "parent_target": "",
                "child_landline_target": self.landline.id,
                "conference_group_target": "",
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
