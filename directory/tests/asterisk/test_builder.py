from datetime import time

from django.test import TestCase, override_settings

from directory.asterisk.builder import build_asterisk_configuration
from directory.models import (
    AllowedChildFamilyRelationship,
    Child,
    ChildBlackoutPeriod,
    ChildLandline,
    ChildLandlineDialShortcut,
    Device,
    DialShortcut,
    ExternalContactPermission,
    ExternalNumberExtension,
    ExternalPhoneNumber,
    Family,
    FamilyContact,
    Parent,
    PublicPhoneNumber,
)


class AsteriskConfigurationBuilderTests(TestCase):
    def setUp(self):
        self.river = Family.objects.create(name="River House")
        self.maple = Family.objects.create(name="Maple House")

        self.alex = Child.objects.create(family=self.river, name="Alex")
        self.emma = Child.objects.create(family=self.maple, name="Emma")
        self.luca = Child.objects.create(family=self.maple, name="Luca")
        self.river_parent = Parent.objects.create(family=self.river, display_name="Mara")
        self.maple_parent = Parent.objects.create(family=self.maple, display_name="Nico")

        self.alex_device = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )
        self.emma_device = Device.objects.create(
            assigned_child=self.emma,
            friendly_name="Emma bedroom phone",
            sip_extension="102",
            sip_username="emma-102",
            sip_secret="secret-e",
        )
        self.inactive_device = Device.objects.create(
            assigned_child=self.luca,
            friendly_name="Luca spare phone",
            sip_extension="103",
            sip_username="luca-103",
            sip_secret="secret-l",
            is_active=False,
        )
        self.river_parent_device = Device.objects.create(
            assigned_parent=self.river_parent,
            friendly_name="Mara kitchen phone",
            sip_extension="201",
            sip_username="mara-201",
            sip_secret="secret-m",
        )
        self.maple_parent_device = Device.objects.create(
            assigned_parent=self.maple_parent,
            friendly_name="Nico kitchen phone",
            sip_extension="202",
            sip_username="nico-202",
            sip_secret="secret-n",
        )
        self.river_family_device = Device.objects.create(
            assigned_family=self.river,
            friendly_name="River House hallway phone",
            sip_extension="301",
            sip_username="river-301",
            sip_secret="secret-r",
        )
        self.maple_family_device = Device.objects.create(
            assigned_family=self.maple,
            friendly_name="Maple House hallway phone",
            sip_extension="302",
            sip_username="maple-302",
            sip_secret="secret-h",
        )

    def test_active_devices_become_stable_sip_endpoints(self):
        configuration = build_asterisk_configuration()

        endpoint_names = [endpoint.endpoint_name for endpoint in configuration.endpoints]

        self.assertEqual(
            endpoint_names,
            [
                "alex-101",
                "emma-102",
                "mara-201",
                "nico-202",
                "river-301",
                "maple-302",
            ],
        )
        self.assertEqual(configuration.endpoints[0].auth_name, "alex-101")
        self.assertEqual(configuration.endpoints[0].aor_name, "alex-101")

    def test_shared_extension_devices_keep_separate_sip_endpoints(self):
        softphone = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex Linphone",
            sip_extension="101",
            sip_username="alex-linphone",
            sip_secret="softphone-secret",
        )

        configuration = build_asterisk_configuration()
        shared_endpoints = [
            endpoint for endpoint in configuration.endpoints if endpoint.extension == "101"
        ]

        self.assertEqual(
            [(endpoint.device_id, endpoint.username) for endpoint in shared_endpoints],
            [
                (self.alex_device.id, "alex-101"),
                (softphone.id, "alex-linphone"),
            ],
        )

    def test_shared_extension_creates_a_rule_for_each_owned_device(self):
        Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex Linphone",
            sip_extension="101",
            sip_username="alex-linphone",
            sip_secret="softphone-secret",
        )

        configuration = build_asterisk_configuration()
        targets = [
            rule.target_endpoint.username
            for rule in configuration.dialplan_rules
            if rule.source_endpoint.device_id == self.river_parent_device.id
            and rule.target_endpoint.extension == "101"
        ]

        self.assertEqual(targets, ["alex-101", "alex-linphone"])

    @override_settings(ASTERISK_OUTBOUND_CALLER_ID="2025550199")
    def test_outbound_caller_id_setting_is_included(self):
        configuration = build_asterisk_configuration()

        self.assertEqual(configuration.outbound_caller_id, "2025550199")

    def test_parent_and_family_devices_become_sip_endpoints(self):
        configuration = build_asterisk_configuration()

        endpoints_by_extension = {
            endpoint.extension: endpoint for endpoint in configuration.endpoints
        }

        self.assertEqual(endpoints_by_extension["201"].owner_type, "parent")
        self.assertEqual(endpoints_by_extension["301"].owner_type, "family")
        self.assertEqual(endpoints_by_extension["201"].family_id, self.river.id)
        self.assertEqual(endpoints_by_extension["301"].family_id, self.river.id)

    def test_active_child_landlines_become_non_sip_routable_endpoints(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertNotIn(
            "2222",
            {endpoint.extension for endpoint in configuration.endpoints},
        )
        self.assertEqual(
            [
                (
                    endpoint.child_id,
                    endpoint.extension,
                    endpoint.normalized_number,
                    endpoint.dial_target,
                )
                for endpoint in configuration.landline_endpoints
            ],
            [(self.alex.id, "2222", "+12125550100", "PJSIP/12125550100@voipms-endpoint")],
        )

    def test_inactive_devices_do_not_appear(self):
        configuration = build_asterisk_configuration()

        device_ids = [endpoint.device_id for endpoint in configuration.endpoints]

        self.assertNotIn(self.inactive_device.id, device_ids)

    def test_inactive_child_landlines_do_not_appear(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.river_parent,
            is_active=False,
        )

        configuration = build_asterisk_configuration()

        self.assertEqual(configuration.landline_endpoints, ())
        self.assertDialplanOmits(configuration, "201", "2222")

    def test_active_public_phone_numbers_become_inbound_numbers(self):
        PublicPhoneNumber.objects.filter(normalized_number="+12025550199").update(
            is_active=True
        )
        PublicPhoneNumber.objects.create(
            normalized_number="212-555-0100",
            label="River public number",
            assigned_family=self.river,
        )
        PublicPhoneNumber.objects.create(
            normalized_number="646-555-0100",
            assigned_family=self.river,
            is_active=False,
        )

        configuration = build_asterisk_configuration()
        numbers_by_normalized_number = {
            number.normalized_number: number
            for number in configuration.public_inbound_numbers
        }

        self.assertIn("+12025550199", numbers_by_normalized_number)
        self.assertIn("+12125550100", numbers_by_normalized_number)
        self.assertNotIn("+16465550100", numbers_by_normalized_number)
        self.assertIsNone(numbers_by_normalized_number["+12025550199"].family_id)
        self.assertEqual(
            numbers_by_normalized_number["+12125550100"].family_id,
            self.river.id,
        )

    def test_approved_external_contact_creates_outbound_rule(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        extension = ExternalNumberExtension.objects.create(
            external_phone_number=number,
            dial_extension="2222",
        )
        ExternalContactPermission.objects.create(
            child=self.alex,
            external_phone_number=number,
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertIn(
            ("101", extension.dial_extension, "+12125550100"),
            {
                (
                    rule.source_endpoint.extension,
                    rule.dialed_extension,
                    rule.normalized_number,
                )
                for rule in configuration.external_dialplan_rules
            },
        )

    def test_family_contact_creates_outbound_rules_for_family_children(self):
        luca = Child.objects.create(family=self.river, name="Luca River")
        luca_device = Device.objects.create(
            assigned_child=luca,
            friendly_name="Luca bedroom phone",
            sip_extension="104",
            sip_username="luca-river-104",
            sip_secret="secret-lr",
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        contact = FamilyContact.objects.create(
            family=self.river,
            external_phone_number=number,
            label="Grandma",
        )

        configuration = build_asterisk_configuration()

        self.assertIn(
            ("101", contact.dial_extension.dial_extension, "+12125550100"),
            {
                (
                    rule.source_endpoint.extension,
                    rule.dialed_extension,
                    rule.normalized_number,
                )
                for rule in configuration.external_dialplan_rules
            },
        )
        self.assertIn(
            (luca_device.sip_extension, contact.dial_extension.dial_extension, "+12125550100"),
            {
                (
                    rule.source_endpoint.extension,
                    rule.dialed_extension,
                    rule.normalized_number,
                )
                for rule in configuration.external_dialplan_rules
            },
        )
        self.assertNotIn(
            ("102", contact.dial_extension.dial_extension, "+12125550100"),
            {
                (
                    rule.source_endpoint.extension,
                    rule.dialed_extension,
                    rule.normalized_number,
                )
                for rule in configuration.external_dialplan_rules
            },
        )

    def test_unapproved_external_contact_does_not_create_outbound_rule(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        ExternalNumberExtension.objects.create(
            external_phone_number=number,
            dial_extension="2222",
        )
        ExternalContactPermission.objects.create(
            child=self.alex,
            external_phone_number=number,
        )

        configuration = build_asterisk_configuration()

        self.assertEqual(configuration.external_dialplan_rules, ())

    def test_approved_external_contact_creates_inbound_rule_for_family_public_number(self):
        public_number = PublicPhoneNumber.objects.create(
            normalized_number="202-555-0198",
            assigned_family=self.river,
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        ExternalContactPermission.objects.create(
            child=self.alex,
            external_phone_number=number,
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertIn(
            (public_number.id, "+12125550100", "101"),
            {
                (
                    rule.public_phone_number_id,
                    rule.caller_normalized_number,
                    rule.target_endpoint.extension,
                )
                for rule in configuration.inbound_external_caller_rules
            },
        )

    def test_family_contact_creates_inbound_rule_for_family_children(self):
        public_number = PublicPhoneNumber.objects.create(
            normalized_number="202-555-0198",
            assigned_family=self.river,
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        FamilyContact.objects.create(
            family=self.river,
            external_phone_number=number,
            label="Grandma",
        )

        configuration = build_asterisk_configuration()

        self.assertIn(
            (public_number.id, "+12125550100", "101"),
            {
                (
                    rule.public_phone_number_id,
                    rule.caller_normalized_number,
                    rule.target_endpoint.extension,
                )
                for rule in configuration.inbound_external_caller_rules
            },
        )
        self.assertNotIn(
            (public_number.id, "+12125550100", "102"),
            {
                (
                    rule.public_phone_number_id,
                    rule.caller_normalized_number,
                    rule.target_endpoint.extension,
                )
                for rule in configuration.inbound_external_caller_rules
            },
        )

    def test_shared_public_number_creates_inbound_rule_for_approved_caller(self):
        public_number = PublicPhoneNumber.objects.get(normalized_number="+12025550199")
        public_number.is_active = True
        public_number.save()
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 646 555 0100")
        ExternalContactPermission.objects.create(
            child=self.alex,
            external_phone_number=number,
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertIn(
            (public_number.id, "+16465550100", "101"),
            {
                (
                    rule.public_phone_number_id,
                    rule.caller_normalized_number,
                    rule.target_endpoint.extension,
                )
                for rule in configuration.inbound_external_caller_rules
            },
        )

    def test_inbound_external_rule_omits_public_number_assigned_to_other_family(self):
        other_family_public_number = PublicPhoneNumber.objects.create(
            normalized_number="212-555-0100",
            assigned_family=self.maple,
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 646 555 0100")
        ExternalContactPermission.objects.create(
            child=self.alex,
            external_phone_number=number,
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertNotIn(
            other_family_public_number.id,
            {
                rule.public_phone_number_id
                for rule in configuration.inbound_external_caller_rules
            },
        )

    def test_shared_public_number_keeps_ambiguous_approved_caller_targets(self):
        public_number = PublicPhoneNumber.objects.get(normalized_number="+12025550199")
        public_number.is_active = True
        public_number.save()
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 646 555 0100")
        ExternalContactPermission.objects.create(
            child=self.alex,
            external_phone_number=number,
            approved_by=self.river_parent,
        )
        ExternalContactPermission.objects.create(
            child=self.emma,
            external_phone_number=number,
            approved_by=self.maple_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertEqual(
            {
                (
                    rule.public_phone_number_id,
                    rule.caller_normalized_number,
                    rule.target_endpoint.extension,
                )
                for rule in configuration.inbound_external_caller_rules
                if rule.public_phone_number_id == public_number.id
            },
            {
                (public_number.id, "+16465550100", "101"),
                (public_number.id, "+16465550100", "102"),
            },
        )

    def test_parent_phone_creates_inbound_rule_for_family_public_number(self):
        public_number = PublicPhoneNumber.objects.create(
            normalized_number="202-555-0198",
            assigned_family=self.river,
        )
        self.river_parent.phone = "212-555-0100"
        self.river_parent.save()

        configuration = build_asterisk_configuration()

        self.assertIn(
            (public_number.id, "+12125550100", "101"),
            {
                (
                    rule.public_phone_number_id,
                    rule.caller_normalized_number,
                    rule.target_endpoint.extension,
                )
                for rule in configuration.inbound_external_caller_rules
            },
        )

    def test_parent_phone_creates_inbound_rule_for_shared_public_number(self):
        public_number = PublicPhoneNumber.objects.get(normalized_number="+12025550199")
        public_number.is_active = True
        public_number.save()
        self.river_parent.phone = "212-555-0100"
        self.river_parent.save()

        configuration = build_asterisk_configuration()

        self.assertIn(
            (public_number.id, "+12125550100", "101"),
            {
                (
                    rule.public_phone_number_id,
                    rule.caller_normalized_number,
                    rule.target_endpoint.extension,
                )
                for rule in configuration.inbound_external_caller_rules
            },
        )

    def test_parent_phone_inbound_rule_targets_child_landline_too(self):
        public_number = PublicPhoneNumber.objects.create(
            normalized_number="202-555-0198",
            assigned_family=self.river,
        )
        self.river_parent.phone = "212-555-0100"
        self.river_parent.save()
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 646 555 0100")
        ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertEqual(
            {
                (
                    rule.public_phone_number_id,
                    rule.caller_normalized_number,
                    rule.target_endpoint.extension,
                )
                for rule in configuration.inbound_external_caller_rules
                if rule.public_phone_number_id == public_number.id
            },
            {
                (public_number.id, "+12125550100", "101"),
                (public_number.id, "+12125550100", "2222"),
            },
        )

    def test_parent_phone_inbound_rule_omits_public_number_assigned_to_other_family(self):
        other_family_public_number = PublicPhoneNumber.objects.create(
            normalized_number="212-555-0100",
            assigned_family=self.maple,
        )
        self.river_parent.phone = "646-555-0100"
        self.river_parent.save()

        configuration = build_asterisk_configuration()

        self.assertNotIn(
            other_family_public_number.id,
            {
                rule.public_phone_number_id
                for rule in configuration.inbound_external_caller_rules
                if rule.caller_normalized_number == "+16465550100"
            },
        )

    def test_shortcut_rules_are_scoped_to_source_device(self):
        DialShortcut.objects.create(
            source_device=self.alex_device,
            digits="1",
            internal_target_device=self.river_parent_device,
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertEqual(len(configuration.shortcut_rules), 1)
        self.assertEqual(configuration.shortcut_rules[0].source_endpoint.extension, "101")
        self.assertEqual(configuration.shortcut_rules[0].digits, "1")
        self.assertEqual(
            configuration.shortcut_rules[0].target_endpoint.extension,
            "201",
        )

    def test_internal_shortcut_targets_every_device_on_shared_extension(self):
        Device.objects.create(
            assigned_parent=self.river_parent,
            friendly_name="Mara Linphone",
            sip_extension="201",
            sip_username="mara-linphone",
            sip_secret="softphone-secret",
        )
        DialShortcut.objects.create(
            source_device=self.alex_device,
            digits="2",
            internal_target_device=self.river_parent_device,
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertEqual(
            [rule.target_endpoint.username for rule in configuration.shortcut_rules],
            ["mara-201", "mara-linphone"],
        )

    def test_external_shortcut_rule_targets_approved_number(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        extension = ExternalNumberExtension.objects.create(
            external_phone_number=number,
            dial_extension="2222",
        )
        ExternalContactPermission.objects.create(
            child=self.alex,
            external_phone_number=number,
            approved_by=self.river_parent,
        )
        DialShortcut.objects.create(
            source_device=self.alex_device,
            digits="2",
            external_target_extension=extension,
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertEqual(configuration.shortcut_rules[0].digits, "2")
        self.assertTrue(configuration.shortcut_rules[0].is_external)
        self.assertEqual(configuration.shortcut_rules[0].normalized_number, "+12125550100")

    def test_parent_phone_shortcut_rule_targets_parent_phone(self):
        self.river_parent.phone = "212-555-0100"
        self.river_parent.save()
        DialShortcut.objects.create(
            source_device=self.alex_device,
            digits="2",
            parent_phone_target=self.river_parent,
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertEqual(configuration.shortcut_rules[0].digits, "2")
        self.assertTrue(configuration.shortcut_rules[0].is_external)
        self.assertEqual(configuration.shortcut_rules[0].normalized_number, "+12125550100")

    def test_child_landline_shortcut_rule_targets_landline_endpoint(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        landline = ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.river_parent,
        )
        DialShortcut.objects.create(
            source_device=self.river_parent_device,
            digits="2",
            child_landline_target=landline,
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertEqual(configuration.shortcut_rules[0].digits, "2")
        self.assertFalse(configuration.shortcut_rules[0].is_external)
        self.assertEqual(configuration.shortcut_rules[0].target_endpoint.extension, "2222")
        self.assertEqual(
            configuration.shortcut_rules[0].target_endpoint.dial_target,
            "PJSIP/12125550100@voipms-endpoint",
        )

    def test_inactive_child_landline_shortcut_rule_is_omitted(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        landline = ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.river_parent,
        )
        DialShortcut.objects.create(
            source_device=self.river_parent_device,
            digits="2",
            child_landline_target=landline,
            approved_by=self.river_parent,
        )
        landline.is_active = False
        landline.save()

        configuration = build_asterisk_configuration()

        self.assertEqual(configuration.shortcut_rules, ())

    def test_same_family_devices_can_call_each_other(self):
        configuration = build_asterisk_configuration()

        self.assertDialplanContains(configuration, "101", "201")
        self.assertDialplanContains(configuration, "101", "301")
        self.assertDialplanContains(configuration, "201", "101")
        self.assertDialplanContains(configuration, "301", "201")

    def test_same_family_devices_can_call_child_landline(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertDialplanContains(configuration, "201", "2222")
        self.assertDialplanContains(configuration, "301", "2222")

    def test_child_blackout_periods_are_attached_to_child_endpoints(self):
        ChildBlackoutPeriod.objects.create(
            child=self.alex,
            label="School night bedtime",
            day_group=ChildBlackoutPeriod.WEEKDAYS,
            start_time=time(20, 30),
            end_time=time(23, 59),
            approved_by=self.river_parent,
        )
        ChildBlackoutPeriod.objects.create(
            child=self.alex,
            label="Weekend late night",
            day_group=ChildBlackoutPeriod.WEEKENDS,
            start_time=time(22, 0),
            end_time=time(23, 59),
            approved_by=self.river_parent,
        )

        configuration = build_asterisk_configuration()
        alex_endpoint = next(
            endpoint
            for endpoint in configuration.endpoints
            if endpoint.extension == "101"
        )
        parent_endpoint = next(
            endpoint
            for endpoint in configuration.endpoints
            if endpoint.extension == "201"
        )

        self.assertEqual(
            [
                (window.time_range, window.days)
                for window in alex_endpoint.blackout_windows
            ],
            [
                ("20:30-23:59", "mon-fri"),
                ("22:00-23:59", "sat-sun"),
            ],
        )
        self.assertEqual(parent_endpoint.blackout_windows, ())

    def test_cross_family_child_to_parent_or_family_requires_child_family_approval(self):
        configuration = build_asterisk_configuration()

        self.assertDialplanOmits(configuration, "101", "202")
        self.assertDialplanOmits(configuration, "202", "101")

        self.approve_child_for_family(self.alex, self.maple)
        configuration = build_asterisk_configuration()

        self.assertDialplanContains(configuration, "101", "202")
        self.assertDialplanContains(configuration, "101", "302")
        self.assertDialplanContains(configuration, "202", "101")
        self.assertDialplanContains(configuration, "302", "101")

    def test_one_sided_approval_does_not_allow_cross_family_child_call(self):
        AllowedChildFamilyRelationship.objects.create(
            child=self.alex,
            target_family=self.maple,
            approved_by_child_family_guardian=self.river_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertDialplanOmits(configuration, "101", "202")
        self.assertDialplanOmits(configuration, "202", "101")

    def test_cross_family_child_to_child_requires_both_child_family_approvals(self):
        self.approve_child_for_family(self.alex, self.maple)

        configuration = build_asterisk_configuration()

        self.assertDialplanOmits(configuration, "101", "102")
        self.assertDialplanOmits(configuration, "102", "101")

        self.approve_child_for_family(self.emma, self.river)
        configuration = build_asterisk_configuration()

        self.assertDialplanContains(configuration, "101", "102")
        self.assertDialplanContains(configuration, "102", "101")

    def test_cross_family_child_landline_requires_existing_relationship_approvals(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        ChildLandline.objects.create(
            child=self.luca,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.maple_parent,
        )

        configuration = build_asterisk_configuration()

        self.assertDialplanOmits(configuration, "101", "2222")
        self.assertDialplanOmits(configuration, "201", "2222")

        self.approve_child_for_family(self.luca, self.river)
        configuration = build_asterisk_configuration()

        self.assertDialplanOmits(configuration, "101", "2222")
        self.assertDialplanContains(configuration, "201", "2222")

        self.approve_child_for_family(self.alex, self.maple)
        configuration = build_asterisk_configuration()

        self.assertDialplanContains(configuration, "101", "2222")

    def test_landline_child_caller_only_gets_permitted_child_inbound_targets(self):
        public_number = PublicPhoneNumber.objects.get(normalized_number="+12025550199")
        public_number.is_active = True
        public_number.save()
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        ChildLandline.objects.create(
            child=self.luca,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.maple_parent,
        )
        self.approve_child_for_family(self.luca, self.river)
        self.approve_child_for_family(self.alex, self.maple)

        configuration = build_asterisk_configuration()

        self.assertEqual(
            {
                (
                    rule.public_phone_number_id,
                    rule.caller_normalized_number,
                    rule.target_endpoint.extension,
                )
                for rule in configuration.inbound_landline_caller_rules
                if rule.public_phone_number_id == public_number.id
            },
            {
                (public_number.id, "+12125550100", "101"),
                (public_number.id, "+12125550100", "102"),
            },
        )

    def test_landline_child_caller_number_is_not_generic_external_caller(self):
        public_number = PublicPhoneNumber.objects.get(normalized_number="+12025550199")
        public_number.is_active = True
        public_number.save()
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.river_parent,
        )
        ExternalContactPermission.objects.create(
            child=self.emma,
            external_phone_number=number,
            approved_by=self.maple_parent,
        )
        self.approve_child_for_family(self.alex, self.maple)
        self.approve_child_for_family(self.emma, self.river)

        configuration = build_asterisk_configuration()

        self.assertNotIn(
            "+12125550100",
            {
                rule.caller_normalized_number
                for rule in configuration.inbound_external_caller_rules
            },
        )
        self.assertIn(
            "+12125550100",
            {
                rule.caller_normalized_number
                for rule in configuration.inbound_landline_caller_rules
            },
        )

    def test_child_landline_shortcut_is_scoped_to_callable_family_and_shared_dids(self):
        shared_number = PublicPhoneNumber.objects.get(normalized_number="+12025550199")
        shared_number.is_active = True
        shared_number.save()
        maple_number = PublicPhoneNumber.objects.create(
            normalized_number="202-555-0198",
            assigned_family=self.maple,
        )
        river_number = PublicPhoneNumber.objects.create(
            normalized_number="202-555-0197",
            assigned_family=self.river,
        )
        source_number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 212 555 0100"
        )
        source = ChildLandline.objects.create(
            child=self.luca,
            external_phone_number=source_number,
            dial_extension="2222",
            approved_by=self.maple_parent,
        )
        self.approve_child_for_family(self.luca, self.river)
        self.approve_child_for_family(self.alex, self.maple)
        self.alex.spoken_name = "AL-eks"
        self.alex.save()
        ChildLandlineDialShortcut.objects.create(
            source_landline=source,
            digits="1",
            target_child=self.alex,
            approved_by=self.maple_parent,
        )

        first = build_asterisk_configuration()
        second = build_asterisk_configuration()

        self.assertEqual(
            self.inbound_shortcut_tuples(first),
            {
                (shared_number.id, "+12125550100", "1", "101", self.alex_device.id),
                (maple_number.id, "+12125550100", "1", "101", self.alex_device.id),
            },
        )
        self.assertEqual(
            first.inbound_landline_shortcut_rules,
            second.inbound_landline_shortcut_rules,
        )
        self.assertNotIn(
            river_number.id,
            {
                rule.public_phone_number_id
                for rule in first.inbound_landline_shortcut_rules
            },
        )
        self.assertEqual(
            {
                rule.target_child_name
                for rule in first.inbound_landline_shortcut_rules
            },
            {"AL-eks"},
        )
        self.assertEqual(
            {prompt.text for prompt in first.spoken_prompts},
            {
                "AL-eks",
                "Dial",
                "for",
                "You may also enter an approved four digit extension.",
            },
        )

    def test_child_landline_shortcut_rings_all_sip_devices_on_shared_extension(self):
        public_number = PublicPhoneNumber.objects.get(normalized_number="+12025550199")
        public_number.is_active = True
        public_number.save()
        softphone = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex softphone",
            sip_extension="101",
            sip_username="alex-softphone",
            sip_secret="secret-softphone",
        )
        fallback_number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 646 555 0100"
        )
        ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=fallback_number,
            dial_extension="3552",
            approved_by=self.river_parent,
        )
        source_number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 212 555 0100"
        )
        source = ChildLandline.objects.create(
            child=self.luca,
            external_phone_number=source_number,
            dial_extension="2222",
            approved_by=self.maple_parent,
        )
        self.approve_child_for_family(self.luca, self.river)
        self.approve_child_for_family(self.alex, self.maple)
        ChildLandlineDialShortcut.objects.create(
            source_landline=source,
            digits="2",
            target_child=self.alex,
            approved_by=self.maple_parent,
        )

        configuration = build_asterisk_configuration()

        alex_shortcuts = {
            (rule.target_endpoint.extension, rule.target_endpoint.device_id)
            for rule in configuration.inbound_landline_shortcut_rules
            if rule.public_phone_number_id == public_number.id
        }
        self.assertEqual(
            alex_shortcuts,
            {("101", self.alex_device.id), ("101", softphone.id)},
        )
        self.assertNotIn(
            "3552",
            {
                rule.target_endpoint.extension
                for rule in configuration.inbound_landline_caller_rules
                if rule.caller_endpoint == next(
                    endpoint
                    for endpoint in configuration.landline_endpoints
                    if endpoint.child_landline_id == source.id
                )
            },
        )

    def test_child_landline_shortcut_falls_back_to_target_landline_without_sip(self):
        public_number = PublicPhoneNumber.objects.get(normalized_number="+12025550199")
        public_number.is_active = True
        public_number.save()
        target = Child.objects.create(family=self.maple, name="Quinn")
        source_number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 212 555 0100"
        )
        target_number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 646 555 0100"
        )
        source = ChildLandline.objects.create(
            child=self.luca,
            external_phone_number=source_number,
            dial_extension="2222",
            approved_by=self.maple_parent,
        )
        target_landline = ChildLandline.objects.create(
            child=target,
            external_phone_number=target_number,
            dial_extension="4663",
            approved_by=self.maple_parent,
        )
        ChildLandlineDialShortcut.objects.create(
            source_landline=source,
            digits="3",
            target_child=target,
            approved_by=self.maple_parent,
        )

        configuration = build_asterisk_configuration()

        shortcut = next(
            rule
            for rule in configuration.inbound_landline_shortcut_rules
            if rule.public_phone_number_id == public_number.id
        )
        self.assertEqual(shortcut.target_endpoint.child_landline_id, target_landline.id)
        self.assertEqual(shortcut.target_endpoint.extension, "4663")

    def test_revoked_permission_retains_shortcut_but_omits_runtime_rule(self):
        public_number = PublicPhoneNumber.objects.get(normalized_number="+12025550199")
        public_number.is_active = True
        public_number.save()
        source_number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 212 555 0100"
        )
        source = ChildLandline.objects.create(
            child=self.luca,
            external_phone_number=source_number,
            dial_extension="2222",
            approved_by=self.maple_parent,
        )
        self.approve_child_for_family(self.luca, self.river)
        reciprocal = self.approve_child_for_family(self.alex, self.maple)
        shortcut = ChildLandlineDialShortcut.objects.create(
            source_landline=source,
            digits="2",
            target_child=self.alex,
            approved_by=self.maple_parent,
        )

        reciprocal.delete()
        configuration = build_asterisk_configuration()

        self.assertTrue(ChildLandlineDialShortcut.objects.filter(pk=shortcut.pk).exists())
        self.assertEqual(configuration.inbound_landline_shortcut_rules, ())
        self.assertEqual(configuration.spoken_prompts, ())

    def test_inactive_child_landline_shortcut_is_omitted(self):
        public_number = PublicPhoneNumber.objects.get(normalized_number="+12025550199")
        public_number.is_active = True
        public_number.save()
        source_number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 212 555 0100"
        )
        source = ChildLandline.objects.create(
            child=self.luca,
            external_phone_number=source_number,
            dial_extension="2222",
            approved_by=self.maple_parent,
        )
        ChildLandlineDialShortcut.objects.create(
            source_landline=source,
            digits="2",
            target_child=self.emma,
            approved_by=self.maple_parent,
            is_active=False,
        )

        configuration = build_asterisk_configuration()

        self.assertEqual(configuration.inbound_landline_shortcut_rules, ())

    def test_cross_family_parent_or_family_devices_cannot_call_each_other(self):
        configuration = build_asterisk_configuration()

        self.assertDialplanOmits(configuration, "201", "202")
        self.assertDialplanOmits(configuration, "301", "302")

    def approve_child_for_family(self, child, target_family):
        child_family_guardian = (
            self.river_parent if child.family == self.river else self.maple_parent
        )
        target_family_guardian = (
            self.river_parent if target_family == self.river else self.maple_parent
        )
        return AllowedChildFamilyRelationship.objects.create(
            child=child,
            target_family=target_family,
            approved_by_child_family_guardian=child_family_guardian,
            approved_by_target_family_guardian=target_family_guardian,
        )

    def assertDialplanContains(self, configuration, source_extension, target_extension):
        self.assertIn(
            (source_extension, target_extension),
            self.dialplan_pairs(configuration),
        )

    def assertDialplanOmits(self, configuration, source_extension, target_extension):
        self.assertNotIn(
            (source_extension, target_extension),
            self.dialplan_pairs(configuration),
        )

    def dialplan_pairs(self, configuration):
        return {
            (
                rule.source_endpoint.extension,
                rule.target_endpoint.extension,
            )
            for rule in configuration.dialplan_rules
        }

    def inbound_shortcut_tuples(self, configuration):
        return {
            (
                rule.public_phone_number_id,
                rule.caller_normalized_number,
                rule.digits,
                rule.target_endpoint.extension,
                getattr(rule.target_endpoint, "device_id", None),
            )
            for rule in configuration.inbound_landline_shortcut_rules
        }
