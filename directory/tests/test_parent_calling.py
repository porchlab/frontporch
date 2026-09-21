from datetime import time
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from directory import models as m
from directory.forms import ShortcutForm
from directory.asterisk.builder import build_asterisk_configuration
from directory.asterisk.renderer import AsteriskConfigRenderer
from directory.phonebook import device_phonebook
from directory.services import shortcut_destinations
from directory.tests.factories import create_user


@override_settings(ASTERISK_OUTBOUND_CALLER_ID="2025550199")
class ParentCallingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.family = m.Family.objects.create(name="Maple")
        cls.parent = m.Parent.objects.create(
            user=create_user(),
            family=cls.family,
            display_name="Taylor",
            phone="2025550188",
            dial_extension="5300",
            call_destination="both",
        )
        cls.child = m.Child.objects.create(family=cls.family, name="Casey")
        cls.source = m.Device.objects.create(
            assigned_child=cls.child,
            friendly_name="Bedroom",
            sip_extension="5301",
            sip_username="fictional-child",
            sip_secret="fictional-child-secret",
        )
        cls.desk = m.Device.objects.create(
            assigned_parent=cls.parent,
            friendly_name="Desk",
            sip_extension="5300",
            sip_username="fictional-desk",
            sip_secret="fictional-desk-secret",
        )
        cls.app = m.Device.objects.create(
            assigned_parent=cls.parent,
            friendly_name="App",
            sip_extension="5300",
            sip_username="fictional-app",
            sip_secret="fictional-app-secret",
        )
        cls.shortcut = m.DialShortcut.objects.create(
            source_device=cls.source,
            parent_target=cls.parent,
            digits="1",
            approved_by=cls.parent,
            label="Mom",
        )

    def rendered_context(self, source=None):
        configuration = build_asterisk_configuration()
        rendered = AsteriskConfigRenderer().render_extensions(configuration)
        username = (source or self.source).sip_username
        return rendered.split(f"[frontporch-{username}]\n", 1)[1].split("\n[", 1)[0]

    def test_extension_and_shortcut_share_each_routing_choice(self):
        for mode, expected in [
            ("frontporch", {"PJSIP/fictional-desk", "PJSIP/fictional-app"}),
            ("phone", {"PJSIP/12025550188@voipms-endpoint"}),
            (
                "both",
                {
                    "PJSIP/fictional-desk",
                    "PJSIP/fictional-app",
                    "PJSIP/12025550188@voipms-endpoint",
                },
            ),
        ]:
            with self.subTest(mode=mode):
                self.parent.call_destination = mode
                self.parent.save()
                config = build_asterisk_configuration()
                self.assertEqual(
                    {
                        rule.target_endpoint.dial_target
                        for rule in config.dialplan_rules
                        if rule.source_endpoint.device_id == self.source.pk
                        and rule.dialed_extension == "5300"
                    },
                    expected,
                )
                context = self.rendered_context()
                self.assertIn("exten => 1,1,Goto(5300,1)", context)
                self.assertEqual(context.count("exten => 5300,1,"), 1)
                dial = next(line for line in context.splitlines() if "Dial(" in line)
                self.assertEqual(
                    set(dial.split("Dial(", 1)[1].split(",30", 1)[0].split("&")),
                    expected,
                )
                self.assertEqual(
                    "Set(CALLERID(num)=2025550199)" in context, mode == "phone"
                )
                self.assertEqual(config, build_asterisk_configuration())

    def test_ring_both_sets_provider_caller_id_only_on_the_trunk_channel(self):
        context = self.rendered_context()
        self.assertNotIn("Set(CALLERID(", context)
        self.assertIn("b(frontporch-outbound-caller-id^s^1(2025550199))", context)
        rendered = AsteriskConfigRenderer().render_extensions(
            build_asterisk_configuration()
        )
        handler = rendered.split("[frontporch-outbound-caller-id]\n", 1)[1].split(
            "\n[", 1
        )[0]
        self.assertEqual(
            handler.strip(),
            'exten => s,1,ExecIf($["${CHANNEL(endpoint)}" = "voipms-endpoint"]'
            "?Set(CALLERID(num)=${ARG1}))\n"
            " same => n,Return()",
        )

    @override_settings(ASTERISK_OUTBOUND_CALLER_ID="")
    def test_ring_both_without_provider_caller_id_keeps_original_identity(self):
        context = self.rendered_context()
        self.assertNotIn("CALLERID(", context)
        self.assertNotIn("b(frontporch-outbound-caller-id", context)
        self.assertIn("PJSIP/fictional-desk", context)
        self.assertIn("PJSIP/12025550188@voipms-endpoint", context)

    def test_phonebook_has_one_parent_and_device_shortcuts_become_parent_aliases(self):
        shortcut = m.DialShortcut.objects.create(
            source_device=self.source,
            internal_target_device=self.desk,
            digits="2",
            approved_by=self.parent,
        )
        shortcut.refresh_from_db()
        self.assertEqual(shortcut.parent_target, self.parent)
        self.assertIsNone(shortcut.internal_target_device_id)
        entries = device_phonebook(self.source)
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0].name, entries[0].extension), ("Taylor", "5300"))
        self.assertEqual([s["digits"] for s in entries[0].shortcuts], ["1", "2"])
        self.assertEqual(
            set(shortcut_destinations(self.source)), {f"parent:{self.parent.pk}"}
        )
        self.client.force_login(self.parent.user)
        response = self.client.get(
            reverse("directory:phonebook", args=[self.source.pk])
        )
        self.assertContains(response, "Taylor", count=1)
        self.assertNotContains(response, self.parent.phone)
        self.assertNotContains(response, "Use shortcut")

    def test_disabled_or_unavailable_parent_has_no_extension_or_shortcut_route(self):
        for mode in ("disabled", "frontporch"):
            with self.subTest(mode=mode):
                m.Device.objects.filter(assigned_parent=self.parent).update(
                    is_active=False
                )
                self.parent.call_destination = mode
                self.parent.save()
                context = self.rendered_context()
                self.assertNotIn("exten => 5300,", context)
                self.assertNotIn("exten => 1,", context)
                self.assertIn("exten => _X!,1,Hangup(21)", context)
                self.assertEqual(device_phonebook(self.source), [])
        self.assertTrue(m.DialShortcut.objects.filter(pk=self.shortcut.pk).exists())

    def test_paused_sip_device_does_not_disable_mobile_or_other_device(self):
        self.desk.is_active = False
        self.desk.save()
        context = self.rendered_context()
        self.assertNotIn("PJSIP/fictional-desk", context)
        self.assertIn("PJSIP/fictional-app", context)
        self.assertIn("PJSIP/12025550188@voipms-endpoint", context)
        self.assertIn("exten => 1,1,Goto(5300,1)", context)

    def test_reassigned_device_shortcut_resolves_to_the_same_parent_everywhere(self):
        sibling = m.Child.objects.create(family=self.family, name="Riley")
        device = m.Device.objects.create(
            assigned_child=sibling,
            friendly_name="Spare",
            sip_extension="5302",
            sip_username="fictional-spare",
            sip_secret="fictional-spare-secret",
        )
        shortcut = m.DialShortcut.objects.create(
            source_device=self.source,
            internal_target_device=device,
            digits="2",
            approved_by=self.parent,
        )
        device.assigned_child = None
        device.assigned_parent = self.parent
        device.sip_extension = self.parent.dial_extension
        device.is_active = False
        device.save()
        shortcut.refresh_from_db()
        form = ShortcutForm(source=self.source, parent=self.parent, instance=shortcut)
        self.assertEqual(form.initial["target"], f"parent:{self.parent.pk}")
        self.assertIn("exten => 2,1,Goto(5300,1)", self.rendered_context())
        entries = device_phonebook(self.source)
        self.assertEqual(len(entries), 1)
        self.assertEqual([s["digits"] for s in entries[0].shortcuts], ["1", "2"])
        self.client.force_login(self.parent.user)
        response = self.client.get(
            reverse("directory:shortcuts", args=[self.source.pk])
        )
        self.assertNotContains(response, "Destination unavailable")

    def test_mobile_only_parent_has_stable_extension_without_a_shortcut(self):
        m.Device.objects.filter(assigned_parent=self.parent).delete()
        self.shortcut.delete()
        self.parent.call_destination = "phone"
        self.parent.phone = "2025550187"
        self.parent.save()
        self.assertEqual(self.parent.dial_extension, "5300")
        self.assertEqual(device_phonebook(self.source)[0].extension, "5300")
        self.assertIn("PJSIP/12025550187@voipms-endpoint", self.rendered_context())

    def test_other_family_and_stale_approval_cannot_use_parent_alias(self):
        other_family = m.Family.objects.create(name="Willow")
        other_parent = m.Parent.objects.create(
            user=create_user(), family=other_family, display_name="Morgan"
        )
        other_child = m.Child.objects.create(family=other_family, name="Alex")
        other_source = m.Device.objects.create(
            assigned_child=other_child,
            friendly_name="Other bedroom",
            sip_extension="5400",
            sip_username="fictional-other",
            sip_secret="fictional-other-secret",
        )
        m.ChildConnection.objects.create(
            child_a=self.child,
            child_b=other_child,
            approved_by_a=self.parent,
            approved_by_b=other_parent,
        )
        # Simulate a stale shortcut after an ownership change without validating it away.
        m.DialShortcut.objects.filter(pk=self.shortcut.pk).update(
            source_device=other_source
        )
        self.assertNotIn("5300", {e.extension for e in device_phonebook(other_source)})
        self.assertNotIn("exten => 5300,", self.rendered_context(other_source))
        self.assertNotIn("exten => 1,", self.rendered_context(other_source))
        m.DialShortcut.objects.filter(pk=self.shortcut.pk).update(
            source_device=self.source, approved_by=other_parent
        )
        self.assertNotIn("exten => 1,", self.rendered_context())
        self.assertEqual(device_phonebook(self.source)[0].shortcuts, [])

    def test_inactive_source_and_revoked_shortcut_do_not_generate_aliases(self):
        for changes in ({"is_active": False}, {"approved_by": None}):
            m.DialShortcut.objects.filter(pk=self.shortcut.pk).update(
                is_active=True, approved_by=self.parent
            )
            m.DialShortcut.objects.filter(pk=self.shortcut.pk).update(**changes)
            self.assertNotIn("exten => 1,", self.rendered_context())
            self.assertEqual(device_phonebook(self.source)[0].shortcuts, [])
        self.source.is_active = False
        self.source.save()
        self.assertEqual(device_phonebook(self.source), [])
        self.assertNotIn(
            self.source.pk,
            {
                rule.source_endpoint.device_id
                for rule in build_asterisk_configuration().dialplan_rules
            },
        )

    def test_parent_calls_keep_same_household_quiet_hours_exception(self):
        m.ChildBlackoutPeriod.objects.create(
            child=self.child,
            approved_by=self.parent,
            label="Homework",
            day_group="every_day",
            start_time=time(16),
            end_time=time(17),
        )
        self.assertNotIn("GotoIfTime", self.rendered_context())

    def test_profile_updates_routing_for_only_the_authenticated_parent_and_logs_it(
        self,
    ):
        self.client.force_login(self.parent.user)
        response = self.client.post(
            reverse("directory:settings"),
            {
                "form": "profile",
                "display_name": "Taylor",
                "phone": self.parent.phone,
                "call_destination": "phone",
                "dial_extension": "5999",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.call_destination, "phone")
        self.assertEqual(self.parent.dial_extension, "5300")
        self.assertTrue(
            self.family.activity.filter(
                actor=self.parent.user,
                description__contains="Calls ring: My phone number",
            ).exists()
        )
        response = self.client.post(
            reverse("directory:settings"),
            {
                "form": "profile",
                "display_name": "Taylor",
                "phone": "",
                "call_destination": "both",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.call_destination, "phone")

    def test_parent_extension_is_reserved_across_all_destinations(self):
        number = m.ExternalPhoneNumber.objects.create(normalized_number="2025550186")
        candidates = [
            m.Parent(
                user=create_user(),
                family=self.family,
                display_name="Morgan",
                dial_extension="5300",
            ),
            m.Device(
                assigned_child=self.child,
                friendly_name="Spare",
                sip_extension="5300",
                sip_username="fictional-spare",
                sip_secret="fictional-secret",
            ),
            m.ExternalNumberExtension(
                external_phone_number=number, dial_extension="5300"
            ),
            m.ChildLandline(
                child=self.child,
                external_phone_number=number,
                approved_by=self.parent,
                dial_extension="5300",
            ),
            m.ConferenceGroup(name="Club", dial_extension="5300"),
        ]
        for candidate in candidates:
            with (
                self.subTest(model=type(candidate).__name__),
                self.assertRaises(ValidationError),
            ):
                candidate.full_clean()
        for allocator in (
            m.ExternalNumberExtension,
            m.ChildLandline,
            m.ConferenceGroup,
        ):
            with patch(
                "directory.models._random_four_digit_extension",
                side_effect=["5300", "5998"],
            ):
                self.assertEqual(allocator._assign_extension(), "5998")

    def test_parent_cannot_steal_existing_number_change_identity_or_inject_config(self):
        for extension in ("5301", "911", "5\n00", "５３００"):
            with self.subTest(extension=extension), self.assertRaises(ValidationError):
                m.Parent(
                    user=create_user(),
                    family=self.family,
                    display_name="Morgan",
                    dial_extension=extension,
                ).full_clean()
        self.parent.dial_extension = "5999"
        with self.assertRaises(ValidationError):
            self.parent.save()
        self.app.sip_extension = "5999"
        with self.assertRaises(ValidationError):
            self.app.save()
