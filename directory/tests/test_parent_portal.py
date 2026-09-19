from datetime import time

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from directory.models import (
    AllowedChildFamilyRelationship,
    Child,
    ChildBlackoutPeriod,
    ConferenceGroup,
    ExternalContactPermission,
    ExternalNumberExtension,
    ExternalPhoneNumber,
    Family,
    FamilyContact,
    Parent,
)


class ParentPortalTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="River House")
        self.other_family = Family.objects.create(name="Maple House")
        self.user = User.objects.create_user(username="mara", password="secret-pass")
        self.parent = Parent.objects.create(
            user=self.user,
            family=self.family,
            display_name="Mara",
            email="mara@example.com",
        )
        self.other_user = User.objects.create_user(username="nico", password="secret-pass")
        self.other_parent = Parent.objects.create(
            user=self.other_user,
            family=self.other_family,
            display_name="Nico",
            email="nico@example.com",
        )
        self.child = Child.objects.create(family=self.family, name="Alex")
        self.other_child = Child.objects.create(family=self.other_family, name="Emma")

    def login(self):
        self.client.login(username="mara", password="secret-pass")

    def test_registration_creates_user_family_and_parent_profile(self):
        response = self.client.post(
            reverse("directory:register"),
            {
                "username": "new-parent",
                "email": "parent@example.com",
                "password1": "strong-test-pass-123",
                "password2": "strong-test-pass-123",
                "family_name": "Oak House",
                "display_name": "Taylor",
                "phone": "212-555-0100",
            },
        )

        self.assertRedirects(response, reverse("directory:dashboard"))
        user = User.objects.get(username="new-parent")
        parent = user.frontporch_parent
        self.assertEqual(parent.family.name, "Oak House")
        self.assertEqual(parent.display_name, "Taylor")
        self.assertEqual(parent.phone, "+12125550100")

    def test_registration_rejects_invalid_parent_phone(self):
        response = self.client.post(
            reverse("directory:register"),
            {
                "username": "new-parent",
                "email": "parent@example.com",
                "password1": "strong-test-pass-123",
                "password2": "strong-test-pass-123",
                "family_name": "Oak House",
                "display_name": "Taylor",
                "phone": "not a number",
            },
        )

        self.assertContains(response, "Enter a valid phone number.", status_code=200)
        self.assertFalse(User.objects.filter(username="new-parent").exists())

    def test_dashboard_only_lists_authenticated_parent_family_children(self):
        self.login()

        response = self.client.get(reverse("directory:dashboard"))

        self.assertContains(response, "Alex")
        self.assertNotContains(response, "Emma")

    def test_parent_can_create_child_only_in_their_family(self):
        self.login()

        self.client.post(
            reverse("directory:child_create"),
            {"name": "Luca", "notes": "Kitchen phone later."},
        )

        child = Child.objects.get(name="Luca")
        self.assertEqual(child.family, self.family)

    def test_parent_cannot_edit_another_family_child(self):
        self.login()

        response = self.client.post(
            reverse("directory:child_update", args=[self.other_child.id]),
            {"name": "Changed", "notes": ""},
        )

        self.assertEqual(response.status_code, 404)
        self.other_child.refresh_from_db()
        self.assertEqual(self.other_child.name, "Emma")

    def test_parent_can_manage_child_blackout_periods_for_family_child(self):
        self.login()

        response = self.client.post(
            reverse("directory:blackout_create", args=[self.child.id]),
            {
                "label": "School night bedtime",
                "day_group": ChildBlackoutPeriod.WEEKDAYS,
                "start_time": "20:30",
                "end_time": "23:00",
                "is_active": "on",
                "notes": "",
            },
        )

        self.assertRedirects(response, reverse("directory:dashboard"))
        blackout = ChildBlackoutPeriod.objects.get(child=self.child)
        self.assertEqual(blackout.approved_by, self.parent)
        self.assertEqual(blackout.start_time, time(20, 30))

        self.client.post(reverse("directory:blackout_deactivate", args=[blackout.id]))
        blackout.refresh_from_db()
        self.assertFalse(blackout.is_active)
        self.assertEqual(blackout.approved_by, self.parent)

    def test_blackout_periods_are_scoped_to_parent_family(self):
        blackout = ChildBlackoutPeriod.objects.create(
            child=self.other_child,
            label="Maple bedtime",
            day_group=ChildBlackoutPeriod.EVERY_DAY,
            start_time=time(20, 0),
            end_time=time(22, 0),
            approved_by=self.other_parent,
        )
        self.login()

        response = self.client.post(reverse("directory:blackout_deactivate", args=[blackout.id]))

        self.assertEqual(response.status_code, 404)
        blackout.refresh_from_db()
        self.assertTrue(blackout.is_active)

    def test_parent_can_add_family_contact_with_dial_extension(self):
        self.login()
        response = self.client.post(
            reverse("directory:contact_create"),
            {
                "label": "Grandma",
                "phone_number": "(212) 555-0100",
                "notes": "",
            },
        )

        self.assertRedirects(response, reverse("directory:dashboard"))
        contact = FamilyContact.objects.get(family=self.family, label="Grandma")
        extension = ExternalNumberExtension.objects.get(
            external_phone_number=contact.external_phone_number
        )
        self.assertEqual(len(extension.dial_extension), 4)

        response = self.client.get(reverse("directory:dashboard"))
        self.assertContains(response, "Grandma")
        self.assertContains(response, "+12125550100")
        self.assertContains(response, f"Ext. {extension.dial_extension}")

    def test_parent_can_remove_family_contact(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        contact = FamilyContact.objects.create(
            family=self.family,
            external_phone_number=number,
            label="Grandma",
        )
        permission = ExternalContactPermission.objects.create(
            child=self.child,
            external_phone_number=number,
            approved_by=self.parent,
        )
        self.login()

        response = self.client.post(
            reverse("directory:contact_delete", args=[contact.id])
        )
        self.assertRedirects(response, reverse("directory:dashboard"))
        self.assertFalse(FamilyContact.objects.filter(id=contact.id).exists())
        self.assertTrue(
            ExternalNumberExtension.objects.filter(external_phone_number=number).exists()
        )
        permission.refresh_from_db()
        self.assertFalse(permission.is_active)

    def test_parent_cannot_remove_other_family_contact(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        contact = FamilyContact.objects.create(
            family=self.other_family,
            external_phone_number=number,
            label="Grandma",
        )
        self.login()

        response = self.client.post(reverse("directory:contact_delete", args=[contact.id]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(FamilyContact.objects.filter(id=contact.id).exists())

    def test_old_family_scope_endpoints_cannot_create_or_approve_permissions(self):
        self.login()
        response = self.client.post(reverse("directory:child_family_relationship_request"),
            {"child": self.child.pk, "target_family_name": self.other_family.name})
        self.assertEqual(response.status_code, 410)
        self.assertFalse(AllowedChildFamilyRelationship.objects.exists())
        relationship = AllowedChildFamilyRelationship.objects.create(child=self.other_child,
            target_family=self.family, approved_by_child_family_guardian=self.other_parent)
        response = self.client.post(reverse("directory:child_family_relationship_approve", args=[relationship.pk]))
        self.assertEqual(response.status_code, 410)
        relationship.refresh_from_db()
        self.assertIsNone(relationship.approved_by_target_family_guardian)

    def test_contact_permission_form_rejects_other_family_child(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        FamilyContact.objects.create(
            family=self.family,
            external_phone_number=number,
            label="Grandma",
        )
        self.login()

        response = self.client.post(
            reverse("directory:external_contact_permission_create"),
            {
                "child": self.other_child.id,
                "external_phone_number": number.id,
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ExternalContactPermission.objects.exists())

    def test_parent_can_create_conference_group_for_own_children(self):
        sibling = Child.objects.create(family=self.family, name="Noah")
        self.login()

        response = self.client.post(
            reverse("directory:conference_group_create"),
            {
                "name": "Siblings",
                "members": [self.child.id, sibling.id],
                "is_active": "on",
                "notes": "",
            },
        )

        self.assertRedirects(response, reverse("directory:dashboard"))
        group = ConferenceGroup.objects.get(name="Siblings")
        self.assertEqual(group.approved_by, self.parent)
        self.assertEqual(set(group.members.values_list("id", flat=True)), {self.child.id, sibling.id})
        self.assertFalse(group.calling_enabled)
        self.assertIsNone(group.dial_extension)
        self.assertTrue(
            LogEntry.objects.filter(
                user=self.user,
                object_id=str(group.id),
                action_flag=ADDITION,
            ).exists()
        )

    def test_parent_update_preserves_staff_calling_fields_and_is_audited(self):
        sibling = Child.objects.create(family=self.family, name="Noah")
        group = ConferenceGroup.objects.create(
            name="Siblings",
            calling_enabled=True,
            dial_extension="4444",
            ring_timeout_seconds=25,
        )
        group.members.set([self.child, sibling])
        self.login()

        response = self.client.post(
            reverse("directory:conference_group_update", args=[group.id]),
            {
                "name": "Kids",
                "members": [self.child.id, sibling.id],
                "is_active": "on",
                "notes": "Updated",
            },
        )

        self.assertRedirects(response, reverse("directory:dashboard"))
        group.refresh_from_db()
        self.assertTrue(group.calling_enabled)
        self.assertEqual(group.dial_extension, "4444")
        self.assertEqual(group.ring_timeout_seconds, 25)
        self.assertTrue(
            LogEntry.objects.filter(
                user=self.user,
                object_id=str(group.id),
                action_flag=CHANGE,
            ).exists()
        )
