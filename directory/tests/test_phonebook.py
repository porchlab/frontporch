from django.db.models import Q
from django.test import TestCase, override_settings
from django.urls import reverse

from directory import models as m
from directory.asterisk.builder import build_asterisk_configuration
from directory.phonebook import device_phonebook, landline_phonebook
from directory.tests.factories import create_user


class PhonebookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.family = m.Family.objects.create(name="Maple")
        cls.remote = m.Family.objects.create(name="Willow")
        cls.parent = m.Parent.objects.create(
            family=cls.family,
            user=create_user(),
            display_name="Taylor",
            phone="2025550199",
        )
        cls.other_parent = m.Parent.objects.create(
            family=cls.remote,
            user=create_user(),
            display_name="Morgan",
        )
        cls.child = m.Child.objects.create(family=cls.family, name="Casey")
        cls.sibling = m.Child.objects.create(family=cls.family, name="Riley")
        cls.friend = m.Child.objects.create(family=cls.remote, name="Alex")
        cls.excluded = m.Child.objects.create(
            family=cls.remote, name="Unapproved child"
        )
        cls.source = cls.device(cls.child, "5101", "Bedroom")
        cls.second_source = cls.device(cls.child, "5109", "Playroom")
        cls.sibling_phone = cls.device(cls.sibling, "5102")
        cls.friend_phone = cls.device(cls.friend, "5201")
        cls.friend_shared_phone = cls.device(cls.friend, "5201", "Another phone")
        cls.excluded_phone = cls.device(cls.excluded, "5202")
        cls.pair = m.ChildConnection.objects.create(
            child_a=cls.child,
            child_b=cls.friend,
            approved_by_a=cls.parent,
            approved_by_b=cls.other_parent,
        )
        cls.parent_device = m.Device.objects.create(
            assigned_parent=cls.parent,
            friendly_name="Office",
            sip_extension="5103",
            sip_username="fictional-parent",
            sip_secret="fictional-parent-secret",
        )
        cls.shared_device = m.Device.objects.create(
            assigned_family=cls.family,
            friendly_name="Kitchen",
            sip_extension="5104",
            sip_username="fictional-kitchen",
            sip_secret="fictional-kitchen-secret",
        )
        cls.remote_parent_device = m.Device.objects.create(
            assigned_parent=cls.other_parent,
            friendly_name="Private office",
            sip_extension="5203",
            sip_username="fictional-remote",
            sip_secret="fictional-remote-secret",
        )
        cls.contact_number = m.ExternalPhoneNumber.objects.create(
            normalized_number="2025550181"
        )
        cls.contact = m.FamilyContact.objects.create(
            family=cls.family,
            external_phone_number=cls.contact_number,
            label="Grandma",
        )
        cls.contact_extension = cls.contact.dial_extension
        m.FamilyContact.objects.create(
            family=cls.remote,
            external_phone_number=cls.contact_number,
            label="Another family's secret label",
        )
        cls.legacy_number = m.ExternalPhoneNumber.objects.create(
            normalized_number="2025550182"
        )
        cls.legacy_extension = m.ExternalNumberExtension.objects.create(
            external_phone_number=cls.legacy_number,
            dial_extension="6102",
        )
        cls.legacy_permission = m.ExternalContactPermission.objects.create(
            child=cls.child,
            external_phone_number=cls.legacy_number,
            approved_by=cls.parent,
        )
        cls.group = m.ConferenceGroup.objects.create(
            name="Saturday club",
            approved_by=cls.parent,
            calling_enabled=True,
            dial_extension="7101",
        )
        cls.group.members.set([cls.child, cls.friend])
        cls.friend_landline = m.ChildLandline.objects.create(
            child=cls.friend,
            approved_by=cls.other_parent,
            dial_extension="6201",
            external_phone_number=m.ExternalPhoneNumber.objects.create(
                normalized_number="2025550183"
            ),
        )
        cls.shortcut = cls.shortcut_to(
            "1", internal_target_device=cls.friend_shared_phone
        )
        cls.shortcut_to(
            "2", internal_target_device=cls.friend_phone, label="Best buddy"
        )
        cls.shortcut_to("3", external_target_extension=cls.contact_extension)
        cls.shortcut_to("4", parent_phone_target=cls.parent)
        cls.shortcut_to("5", conference_group_target=cls.group)
        cls.shortcut_to("6", child_landline_target=cls.friend_landline)
        cls.shortcut_to("7", internal_target_device=cls.sibling_phone, is_active=False)

    @classmethod
    def device(cls, child, extension, name="Bedroom phone", **kwargs):
        return m.Device.objects.create(
            assigned_child=child,
            friendly_name=name,
            sip_extension=extension,
            sip_username=f"fictional-{child.pk}-{extension}-{name}",
            sip_secret="fictional-device-secret",
            **kwargs,
        )

    @classmethod
    def shortcut_to(cls, digits, **kwargs):
        return m.DialShortcut.objects.create(
            source_device=cls.source,
            digits=digits,
            approved_by=cls.parent,
            **kwargs,
        )

    def setUp(self):
        self.client.force_login(self.parent.user)
        self.url = reverse("directory:phonebook", args=[self.source.pk])

    def entries(self):
        return {entry.extension: entry for entry in device_phonebook(self.source)}

    def test_all_extensions_match_generated_routes_and_shared_phones_are_deduplicated(
        self,
    ):
        config = build_asterisk_configuration()
        expected = (
            {
                rule.target_endpoint.extension
                for rule in config.dialplan_rules
                if rule.source_endpoint.device_id == self.source.pk
            }
            | {
                rule.dialed_extension
                for rule in config.external_dialplan_rules
                if rule.source_endpoint.device_id == self.source.pk
            }
            | {
                route.dial_extension
                for route in config.conference_routes
                if route.member_for_child(self.child.pk)
            }
        )
        entries = device_phonebook(self.source)
        self.assertEqual(
            {entry.extension for entry in entries if entry.extension}, expected
        )
        self.assertEqual(sum(entry.extension == "5201" for entry in entries), 1)
        self.assertEqual(
            [shortcut["digits"] for shortcut in self.entries()["5201"].shortcuts],
            ["1", "2"],
        )
        self.assertEqual(self.entries()["5102"].shortcuts, [])
        expected_shortcuts = {
            rule.digits
            for rule in config.shortcut_rules
            if rule.source_endpoint.device_id == self.source.pk
        }
        self.assertEqual(
            {s["digits"] for e in entries for s in e.shortcuts}, expected_shortcuts
        )
        self.assertEqual(device_phonebook(self.source), entries)

    def test_preview_is_low_ink_by_default_and_color_is_explicit(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'class="monochrome"')
        self.assertContains(response, "Casey’s")
        self.assertContains(response, "Grandma")
        self.assertContains(response, "Best buddy")
        self.assertContains(response, "Use shortcut")
        self.assertContains(response, "Quiet hours still apply")
        self.assertContains(response, "Download PDF")
        self.assertContains(response, "US Letter")
        self.assertContains(response, 'src="/static/directory/phonebook-pdf.js"')
        self.assertContains(response, 'src="/static/directory/phonebook-fonts.js"')
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertContains(
            self.client.get(self.url, {"style": "color"}), 'class="color"'
        )
        self.assertContains(
            self.client.get(self.url, {"style": "unknown"}), 'class="monochrome"'
        )

    def test_html_does_not_leak_secrets_numbers_or_other_family_labels(self):
        response = self.client.get(self.url)
        for value in [
            self.source.sip_secret,
            self.source.sip_username,
            self.parent.phone,
            self.contact_number.normalized_number,
            self.legacy_number.normalized_number,
            self.friend_landline.external_phone_number.normalized_number,
            "Another family's secret label",
            self.excluded.name,
            self.excluded_phone.sip_extension,
            self.remote_parent_device.sip_extension,
        ]:
            with self.subTest(value=value):
                self.assertNotContains(response, value)

    def test_shortcuts_do_not_transfer_to_another_phone_of_same_child(self):
        entries = device_phonebook(self.second_source)
        self.assertTrue(entries)
        self.assertTrue(all(not entry.shortcuts for entry in entries))
        self.assertNotIn("", {entry.extension for entry in entries})

    def test_revoked_relationship_removes_destinations_and_stale_shortcuts(self):
        self.pair.is_active = False
        self.pair.save()
        entries = self.entries()
        self.assertNotIn("5201", entries)
        self.assertNotIn("6201", entries)
        self.assertIn("7101", entries)  # Explicit group membership is independent.
        self.assertTrue(m.DialShortcut.objects.filter(pk=self.shortcut.pk).exists())

    def test_pending_invitation_grants_no_phonebook_access(self):
        self.pair.delete()
        invitation = m.ConnectionInvitation.objects.create(
            source_family=self.family,
            target_family=self.remote,
            sent_by=self.parent,
        )
        invitation.source_children.add(self.child)
        self.assertNotIn("5201", self.entries())

    def test_removed_contact_and_legacy_grant_remove_external_extensions(self):
        self.contact.delete()
        self.legacy_permission.approved_by = None
        self.legacy_permission.save()
        entries = self.entries()
        self.assertNotIn(self.contact_extension.dial_extension, entries)
        self.assertNotIn("6102", entries)

    def test_inactive_targets_and_unapproved_shortcuts_are_omitted(self):
        m.Device.objects.filter(assigned_child=self.friend).update(is_active=False)
        m.ChildLandline.objects.filter(pk=self.friend_landline.pk).update(
            is_active=False
        )
        m.ExternalNumberExtension.objects.filter(pk=self.contact_extension.pk).update(
            is_active=False
        )
        m.DialShortcut.objects.filter(parent_phone_target=self.parent).update(
            approved_by=None
        )
        entries = self.entries()
        for extension in ["5201", "6201", self.contact_extension.dial_extension, ""]:
            self.assertNotIn(extension, entries)

    def test_shortcut_to_inactive_shared_device_is_not_printed(self):
        m.Device.objects.filter(pk=self.friend_shared_phone.pk).update(is_active=False)
        self.assertEqual([s["digits"] for s in self.entries()["5201"].shortcuts], ["2"])

    def test_group_requires_calling_enabled_and_current_membership(self):
        for changes in [{"calling_enabled": False}, {"is_active": False}]:
            with self.subTest(changes=changes):
                m.ConferenceGroup.objects.filter(pk=self.group.pk).update(**changes)
                self.assertNotIn("7101", self.entries())
                m.ConferenceGroup.objects.filter(pk=self.group.pk).update(
                    calling_enabled=True, is_active=True
                )
        self.group.members.remove(self.child)
        self.assertNotIn("7101", self.entries())

    def test_inactive_source_and_empty_phonebook(self):
        m.Device.objects.filter(pk=self.source.pk).update(is_active=False)
        response = self.client.get(self.url)
        self.assertEqual(response.context["entries"], [])
        self.assertContains(response, "This phone is not enabled yet")
        child = m.Child.objects.create(family=self.remote, name="New child")
        device = self.device(child, "5901")
        # Own-family phones are allowed, so deactivate them for the empty case.
        m.Device.objects.filter(
            Q(assigned_child__family=self.remote)
            | Q(assigned_parent__family=self.remote)
        ).exclude(pk=device.pk).update(is_active=False)
        m.ChildLandline.objects.filter(child__family=self.remote).update(
            is_active=False
        )
        m.FamilyContact.objects.filter(family=self.remote).delete()
        self.assertEqual(device_phonebook(device), [])

    def test_only_own_family_guardians_can_read_phonebook(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.other_parent.user)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        m.Parent.objects.filter(pk=self.parent.pk).update(is_guardian=False)
        self.client.force_login(self.parent.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(create_user(is_staff=True))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_parent_phone_cannot_be_used_as_child_phonebook_source(self):
        self.assertEqual(
            self.client.get(
                reverse("directory:phonebook", args=[self.parent_device.pk])
            ).status_code,
            404,
        )
        self.assertEqual(self.client.post(self.url).status_code, 405)

    @override_settings(ROOT_URLCONF="frontporch.public_urls")
    def test_public_portal_has_same_guardian_only_route(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.force_login(self.other_parent.user)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_escaped_names_and_entry_links(self):
        self.contact.label = '<script>alert("hello")</script>'
        self.contact.save()
        response = self.client.get(self.url)
        self.assertNotContains(response, self.contact.label)
        self.assertContains(response, "&lt;script&gt;")
        for route, args in [
            ("children", []),
            ("child_detail", [self.child.pk]),
            ("shortcuts", [self.source.pk]),
        ]:
            self.assertContains(
                self.client.get(reverse("directory:" + route, args=args)), self.url
            )

    def make_landline_source(self):
        landline = m.ChildLandline.objects.create(
            child=self.child,
            approved_by=self.parent,
            dial_extension="6301",
            external_phone_number=m.ExternalPhoneNumber.objects.create(
                normalized_number="2025550184"
            ),
        )
        self.public_number = m.PublicPhoneNumber.objects.create(
            normalized_number="2025550185"
        )
        m.ChildLandlineDialShortcut.objects.create(
            source_landline=landline,
            target_child=self.friend,
            digits="1",
            approved_by=self.parent,
        )
        return landline

    def test_landline_routes_match_pbx_and_use_sip_before_landline(self):
        source = self.make_landline_source()
        book = landline_phonebook(source)
        config = build_asterisk_configuration()
        expected = {
            r.target_endpoint.extension
            for r in config.inbound_landline_caller_rules
            if r.caller_endpoint.child_landline_id == source.pk
        }
        self.assertEqual({e.extension for e in book["entries"]}, expected)
        self.assertEqual(expected, {"5102", "5201"})
        self.assertEqual(
            {s["digits"] for e in book["entries"] for s in e.shortcuts}, {"1"}
        )
        m.Device.objects.filter(assigned_child=self.friend).update(is_active=False)
        self.assertEqual(
            {e.extension for e in landline_phonebook(source)["entries"]},
            {"5102", "6201"},
        )

    def test_landline_scope_revocation_and_direct_call_instructions(self):
        source = self.make_landline_source()
        url = reverse("directory:landline_phonebook", args=[source.pk])
        self.assertContains(self.client.get(url), self.public_number.normalized_number)
        self.assertNotContains(
            self.client.get(url), source.external_phone_number.normalized_number
        )
        self.pair.is_active = False
        self.pair.save()
        response = self.client.get(url)
        self.assertContains(response, "Your call connects directly to Riley")
        self.assertEqual(response.context["entries"][0].shortcuts, [])
        self.assertNotContains(response, self.friend.name)
        self.client.force_login(self.other_parent.user)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_landline_needs_active_dial_in_number_for_its_family(self):
        source = self.make_landline_source()
        self.public_number.assigned_family = self.remote
        self.public_number.save()
        book = landline_phonebook(source)
        self.assertEqual(book["dial_in_numbers"], [])
        self.assertEqual(book["entries"], [])
        source.is_active = False
        source.save()
        self.assertEqual(landline_phonebook(source)["entries"], [])
