from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase

from directory.models import (
    AllowedChildFamilyRelationship,
    Child,
    ChildConnection,
    ChildBlackoutPeriod,
    ChildLandline,
    ChildLandlineDialShortcut,
    ConferenceGroup,
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
from directory.services import children_may_conference


class DirectoryDomainTests(TestCase):
    def setUp(self):
        self.family_a = Family.objects.create(name="River House")
        self.family_b = Family.objects.create(name="Maple House")
        self.alex = Child.objects.create(family=self.family_a, name="Alex")
        self.emma = Child.objects.create(family=self.family_b, name="Emma")
        self.luca = Child.objects.create(family=self.family_b, name="Luca")
        self.river_parent = Parent.objects.create(family=self.family_a, display_name="Mara")
        self.maple_parent = Parent.objects.create(family=self.family_b, display_name="Nico")

    def test_child_spoken_menu_name_uses_optional_pronunciation_override(self):
        self.assertEqual(self.alex.spoken_menu_name, "Alex")

        self.alex.spoken_name = "AL-eks"

        self.assertEqual(self.alex.name, "Alex")
        self.assertEqual(self.alex.spoken_menu_name, "AL-eks")

    def test_child_spoken_menu_name_ignores_whitespace_only_override(self):
        self.alex.spoken_name = "   "

        self.assertEqual(self.alex.spoken_menu_name, "Alex")

    def test_phone_number_normalization_uses_e164(self):
        number = ExternalPhoneNumber.objects.create(normalized_number="(212) 555-0100")

        self.assertEqual(number.normalized_number, "+12125550100")

    def test_invalid_phone_number_is_rejected(self):
        with self.assertRaises(ValidationError):
            ExternalPhoneNumber.objects.create(normalized_number="not a number")

    def test_parent_phone_number_normalizes_to_e164(self):
        parent = Parent.objects.create(
            family=self.family_a,
            display_name="Sofia",
            phone="(212) 555-0100",
        )

        self.assertEqual(parent.phone, "+12125550100")

    def test_parent_phone_number_rejects_invalid_value(self):
        with self.assertRaises(ValidationError):
            Parent.objects.create(
                family=self.family_a,
                display_name="Sofia",
                phone="not a number",
            )

    def test_external_phone_number_manager_deduplicates_normalized_numbers(self):
        first, first_created = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 212 555 0100"
        )
        second, second_created = ExternalPhoneNumber.objects.get_or_create_normalized(
            "(212) 555-0100"
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first, second)
        self.assertEqual(ExternalPhoneNumber.objects.count(), 1)

    def test_public_phone_number_normalizes_and_can_be_shared_or_family_owned(self):
        shared = PublicPhoneNumber.objects.create(
            normalized_number="646-555-0100",
            label="Shared test DID",
            provider_name="VoIP.ms",
        )
        family_owned = PublicPhoneNumber.objects.create(
            normalized_number="212-555-0100",
            label="River public number",
            assigned_family=self.family_a,
        )

        self.assertEqual(shared.normalized_number, "+16465550100")
        self.assertTrue(shared.is_shared)
        self.assertEqual(family_owned.normalized_number, "+12125550100")
        self.assertFalse(family_owned.is_shared)

    def test_multiple_family_contacts_can_reference_same_external_number(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")

        sophia = FamilyContact.objects.create(
            family=self.family_a,
            external_phone_number=number,
            label="Sophia",
        )
        sophie = FamilyContact.objects.create(
            family=self.family_b,
            external_phone_number=number,
            label="Sophie",
        )

        self.assertEqual(sophia.external_phone_number, sophie.external_phone_number)
        self.assertEqual(number.family_contacts.count(), 2)

    def test_family_contact_creates_reusable_external_extension(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")

        contact = FamilyContact.objects.create(
            family=self.family_a,
            external_phone_number=number,
            label="Grandma",
        )
        second_contact = FamilyContact.objects.create(
            family=self.family_b,
            external_phone_number=number,
            label="Grandmother",
        )

        self.assertIsNotNone(contact.dial_extension)
        self.assertEqual(len(contact.dial_extension.dial_extension), 4)
        self.assertEqual(contact.dial_extension, second_contact.dial_extension)

    def test_external_number_extension_assigns_unused_four_digit_extension(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")

        extension = ExternalNumberExtension.objects.create(external_phone_number=number)

        self.assertEqual(len(extension.dial_extension), 4)
        self.assertTrue(extension.dial_extension.isdigit())

    def test_external_number_extension_rejects_device_extension_conflict(self):
        Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="2222",
            sip_username="alex-2222",
            sip_secret="secret-a",
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")

        with self.assertRaises(ValidationError):
            ExternalNumberExtension.objects.create(
                external_phone_number=number,
                dial_extension="2222",
            )

    def test_device_rejects_external_number_extension_conflict(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        ExternalNumberExtension.objects.create(
            external_phone_number=number,
            dial_extension="2222",
        )

        with self.assertRaises(ValidationError):
            Device.objects.create(
                assigned_child=self.alex,
                friendly_name="Alex bedroom phone",
                sip_extension="2222",
                sip_username="alex-2222",
                sip_secret="secret-a",
            )

    def test_child_landline_assigns_unused_four_digit_extension(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("(212) 555-0100")

        landline = ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=number,
            approved_by=self.river_parent,
        )

        self.assertEqual(number.normalized_number, "+12125550100")
        self.assertEqual(len(landline.dial_extension), 4)
        self.assertTrue(landline.dial_extension.isdigit())

    def test_child_landline_requires_child_family_approval(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")

        with self.assertRaises(ValidationError):
            ChildLandline.objects.create(
                child=self.alex,
                external_phone_number=number,
                approved_by=self.maple_parent,
            )

    def test_child_landline_rejects_device_extension_conflict(self):
        Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="2222",
            sip_username="alex-2222",
            sip_secret="secret-a",
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")

        with self.assertRaises(ValidationError):
            ChildLandline.objects.create(
                child=self.alex,
                external_phone_number=number,
                dial_extension="2222",
                approved_by=self.river_parent,
            )

    def test_child_landline_rejects_external_number_extension_conflict(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        other_number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 646 555 0100"
        )
        ExternalNumberExtension.objects.create(
            external_phone_number=other_number,
            dial_extension="2222",
        )

        with self.assertRaises(ValidationError):
            ChildLandline.objects.create(
                child=self.alex,
                external_phone_number=number,
                dial_extension="2222",
                approved_by=self.river_parent,
            )

    def test_device_rejects_child_landline_extension_conflict(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.river_parent,
        )

        with self.assertRaises(ValidationError):
            Device.objects.create(
                assigned_child=self.emma,
                friendly_name="Emma bedroom phone",
                sip_extension="2222",
                sip_username="emma-2222",
                sip_secret="secret-e",
            )

    def test_child_landline_rejects_duplicate_active_landline_for_child(self):
        first_number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 212 555 0100"
        )
        second_number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            "+1 646 555 0100"
        )
        ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=first_number,
            dial_extension="2222",
            approved_by=self.river_parent,
        )

        with self.assertRaises(ValidationError):
            ChildLandline.objects.create(
                child=self.alex,
                external_phone_number=second_number,
                dial_extension="3333",
                approved_by=self.river_parent,
            )

    def test_child_landline_shortcut_accepts_digits_one_through_nine(self):
        source = self._create_landline(self.alex, self.river_parent)
        target = Child.objects.create(family=self.family_a, name="Rowan")
        self._create_child_device(target, "3552", "rowan")

        shortcut = ChildLandlineDialShortcut.objects.create(
            source_landline=source,
            digits="1",
            target_child=target,
            approved_by=self.river_parent,
            label="Rowan",
        )

        self.assertEqual(shortcut.target_child, target)
        invalid = ChildLandlineDialShortcut(
            source_landline=source,
            digits="0",
            target_child=target,
            approved_by=self.river_parent,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_child_landline_shortcut_requires_unique_digit_and_target(self):
        source = self._create_landline(self.alex, self.river_parent)
        rowan = Child.objects.create(family=self.family_a, name="Rowan")
        quinn = Child.objects.create(family=self.family_a, name="Quinn")
        self._create_child_device(rowan, "3552", "rowan")
        self._create_child_device(quinn, "4663", "quinn")
        ChildLandlineDialShortcut.objects.create(
            source_landline=source,
            digits="2",
            target_child=rowan,
            approved_by=self.river_parent,
        )

        with self.assertRaises(ValidationError):
            ChildLandlineDialShortcut.objects.create(
                source_landline=source,
                digits="2",
                target_child=quinn,
                approved_by=self.river_parent,
            )
        with self.assertRaises(ValidationError):
            ChildLandlineDialShortcut.objects.create(
                source_landline=source,
                digits="3",
                target_child=rowan,
                approved_by=self.river_parent,
            )

    def test_child_landline_shortcut_requires_source_family_approval(self):
        source = self._create_landline(self.alex, self.river_parent)
        target = Child.objects.create(family=self.family_a, name="Rowan")
        self._create_child_device(target, "3552", "rowan")

        with self.assertRaises(ValidationError):
            ChildLandlineDialShortcut.objects.create(
                source_landline=source,
                digits="2",
                target_child=target,
                approved_by=self.maple_parent,
            )

    def test_child_landline_shortcut_rejects_self_target(self):
        source = self._create_landline(self.alex, self.river_parent)

        with self.assertRaises(ValidationError):
            ChildLandlineDialShortcut.objects.create(
                source_landline=source,
                digits="2",
                target_child=self.alex,
                approved_by=self.river_parent,
            )

    def test_child_landline_shortcut_requires_explicit_child_connection(self):
        source = self._create_landline(self.alex, self.river_parent)
        self._create_child_device(self.emma, "3552", "emma")

        with self.assertRaises(ValidationError):
            ChildLandlineDialShortcut.objects.create(
                source_landline=source,
                digits="2",
                target_child=self.emma,
                approved_by=self.river_parent,
            )

        self._approve_child_for_family(self.alex, self.family_b)
        with self.assertRaises(ValidationError):
            ChildLandlineDialShortcut.objects.create(
                source_landline=source,
                digits="2",
                target_child=self.emma,
                approved_by=self.river_parent,
            )

        self._connect_children(self.alex, self.emma)
        shortcut = ChildLandlineDialShortcut.objects.create(
            source_landline=source,
            digits="2",
            target_child=self.emma,
            approved_by=self.river_parent,
        )
        self.assertTrue(shortcut.is_active)

    def test_child_landline_shortcut_rejects_inactive_source(self):
        source = self._create_landline(self.alex, self.river_parent)
        source.is_active = False
        source.save()
        target = Child.objects.create(family=self.family_a, name="Rowan")
        self._create_child_device(target, "3552", "rowan")

        with self.assertRaises(ValidationError):
            ChildLandlineDialShortcut.objects.create(
                source_landline=source,
                digits="2",
                target_child=target,
                approved_by=self.river_parent,
            )

    def test_child_landline_shortcut_rejects_unroutable_target(self):
        source = self._create_landline(self.alex, self.river_parent)
        target = Child.objects.create(family=self.family_a, name="Rowan")

        with self.assertRaises(ValidationError):
            ChildLandlineDialShortcut.objects.create(
                source_landline=source,
                digits="2",
                target_child=target,
                approved_by=self.river_parent,
            )

    def test_child_landline_shortcut_detects_permission_revocation(self):
        source = self._create_landline(self.alex, self.river_parent)
        self._create_child_device(self.emma, "3552", "emma")
        reciprocal = self._connect_children(self.alex, self.emma)
        shortcut = ChildLandlineDialShortcut.objects.create(
            source_landline=source,
            digits="2",
            target_child=self.emma,
            approved_by=self.river_parent,
        )

        reciprocal.delete()

        with self.assertRaises(ValidationError):
            shortcut.full_clean()

        shortcut.is_active = False
        shortcut.save()

        self.assertFalse(shortcut.is_active)

    def _create_landline(self, child, approved_by, number="+1 212 555 0100"):
        external_number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(number)
        return ChildLandline.objects.create(
            child=child,
            external_phone_number=external_number,
            approved_by=approved_by,
        )

    def _create_child_device(self, child, extension, username):
        return Device.objects.create(
            assigned_child=child,
            friendly_name=f"{child.name} bedroom phone",
            sip_extension=extension,
            sip_username=username,
            sip_secret="secret",
        )

    def _connect_children(self, first, second):
        a, b = sorted((first, second), key=lambda child: child.pk)
        return ChildConnection.objects.create(child_a=a, child_b=b,
            approved_by_a=a.family.parents.first(), approved_by_b=b.family.parents.first())

    def _approve_child_for_family(self, child, target_family):
        return AllowedChildFamilyRelationship.objects.create(
            child=child,
            target_family=target_family,
            approved_by_child_family_guardian=(
                self.river_parent if child.family_id == self.family_a.id else self.maple_parent
            ),
            approved_by_target_family_guardian=(
                self.river_parent
                if target_family.id == self.family_a.id
                else self.maple_parent
            ),
        )

    def test_device_can_belong_to_child_parent_or_family(self):
        child_device = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )
        parent_device = Device.objects.create(
            assigned_parent=self.river_parent,
            friendly_name="Mara kitchen phone",
            sip_extension="201",
            sip_username="mara-201",
            sip_secret="secret-m",
        )
        family_device = Device.objects.create(
            assigned_family=self.family_a,
            friendly_name="River hallway phone",
            sip_extension="301",
            sip_username="river-301",
            sip_secret="secret-r",
        )

        self.assertEqual(child_device.owner_type, "child")
        self.assertEqual(parent_device.owner_type, "parent")
        self.assertEqual(family_device.owner_type, "family")
        self.assertEqual(child_device.owning_family, self.family_a)
        self.assertEqual(parent_device.owning_family, self.family_a)
        self.assertEqual(family_device.owning_family, self.family_a)

    def test_devices_for_same_owner_may_share_extension_with_separate_credentials(self):
        ata = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex ATA",
            sip_extension="101",
            sip_username="alex-ata",
            sip_secret="ata-secret",
        )
        softphone = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex Linphone",
            sip_extension="101",
            sip_username="alex-linphone",
            sip_secret="linphone-secret",
        )

        self.assertEqual(ata.sip_extension, softphone.sip_extension)
        self.assertNotEqual(ata.sip_username, softphone.sip_username)
        self.assertNotEqual(ata.sip_secret, softphone.sip_secret)

    def test_devices_for_different_owners_may_not_share_extension(self):
        Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex ATA",
            sip_extension="101",
            sip_username="alex-ata",
            sip_secret="ata-secret",
        )

        with self.assertRaisesMessage(
            ValidationError,
            "This extension is already assigned to a different child, parent, or family.",
        ):
            Device.objects.create(
                assigned_child=self.emma,
                friendly_name="Emma Linphone",
                sip_extension="101",
                sip_username="emma-linphone",
                sip_secret="linphone-secret",
            )

    def test_parent_and_child_devices_may_not_share_extension(self):
        Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex ATA",
            sip_extension="101",
            sip_username="alex-ata",
            sip_secret="ata-secret",
        )

        with self.assertRaises(ValidationError):
            Device.objects.create(
                assigned_parent=self.river_parent,
                friendly_name="Mara Linphone",
                sip_extension="101",
                sip_username="mara-linphone",
                sip_secret="linphone-secret",
            )

    def test_device_requires_exactly_one_owner(self):
        unassigned_device = Device(
            friendly_name="Unassigned phone",
            sip_extension="401",
            sip_username="unassigned-401",
            sip_secret="secret-u",
        )
        multi_owner_device = Device(
            assigned_child=self.alex,
            assigned_parent=self.river_parent,
            friendly_name="Too many owners phone",
            sip_extension="402",
            sip_username="multi-402",
            sip_secret="secret-t",
        )

        with self.assertRaises(ValidationError):
            unassigned_device.full_clean()
        with self.assertRaises(ValidationError):
            multi_owner_device.full_clean()

    def test_external_contact_permission_requires_child_family_approval(self):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        permission = ExternalContactPermission(
            child=self.alex,
            external_phone_number=number,
            approved_by=self.maple_parent,
        )

        with self.assertRaises(ValidationError):
            permission.full_clean()

    def test_child_blackout_period_requires_child_family_approval(self):
        blackout = ChildBlackoutPeriod(
            child=self.alex,
            label="School night bedtime",
            day_group=ChildBlackoutPeriod.WEEKDAYS,
            start_time=time(20, 30),
            end_time=time(23, 59),
            approved_by=self.maple_parent,
        )

        with self.assertRaises(ValidationError):
            blackout.full_clean()

    def test_child_blackout_period_requires_end_after_start(self):
        blackout = ChildBlackoutPeriod(
            child=self.alex,
            label="Invalid overnight period",
            day_group=ChildBlackoutPeriod.WEEKENDS,
            start_time=time(21, 0),
            end_time=time(8, 0),
            approved_by=self.river_parent,
        )

        with self.assertRaises(ValidationError):
            blackout.full_clean()

    def test_child_blackout_period_exposes_asterisk_time_window(self):
        blackout = ChildBlackoutPeriod.objects.create(
            child=self.alex,
            label="Weekend late night",
            day_group=ChildBlackoutPeriod.WEEKENDS,
            start_time=time(22, 0),
            end_time=time(23, 59),
            approved_by=self.river_parent,
        )

        self.assertEqual(blackout.asterisk_days, "sat-sun")
        self.assertEqual(blackout.asterisk_time_range, "22:00-23:59")

    def test_dial_shortcut_digits_are_limited_to_one_through_nine(self):
        device = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )
        target = Device.objects.create(
            assigned_parent=self.river_parent,
            friendly_name="Mara kitchen phone",
            sip_extension="201",
            sip_username="mara-201",
            sip_secret="secret-m",
        )

        shortcut = DialShortcut.objects.create(
            source_device=device,
            digits="1",
            internal_target_device=target,
        )

        self.assertEqual(shortcut.digits, "1")
        with self.assertRaisesMessage(
            ValidationError,
            "Shortcut digits must be one of 1 through 9.",
        ):
            DialShortcut.objects.create(
                source_device=device,
                digits="0",
                internal_target_device=target,
            )

    def test_dial_shortcut_requires_existing_permission(self):
        source = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )
        target = Device.objects.create(
            assigned_child=self.emma,
            friendly_name="Emma bedroom phone",
            sip_extension="102",
            sip_username="emma-102",
            sip_secret="secret-e",
        )

        with self.assertRaises(ValidationError):
            DialShortcut.objects.create(
                source_device=source,
                digits="2",
                internal_target_device=target,
            )

    def test_dial_shortcut_requires_source_family_approval(self):
        source = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )
        target = Device.objects.create(
            assigned_parent=self.river_parent,
            friendly_name="Mara kitchen phone",
            sip_extension="201",
            sip_username="mara-201",
            sip_secret="secret-m",
        )

        with self.assertRaises(ValidationError):
            DialShortcut.objects.create(
                source_device=source,
                digits="2",
                internal_target_device=target,
                approved_by=self.maple_parent,
            )

    def test_dial_shortcut_can_target_family_contact_external_number(self):
        source = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        extension = ExternalNumberExtension.objects.create(
            external_phone_number=number,
            dial_extension="2222",
        )
        FamilyContact.objects.create(
            family=self.family_a,
            external_phone_number=number,
            label="Grandma",
        )

        shortcut = DialShortcut.objects.create(
            source_device=source,
            digits="2",
            external_target_extension=extension,
            approved_by=self.river_parent,
        )

        self.assertEqual(shortcut.digits, "2")

    def test_dial_shortcut_can_target_same_family_parent_phone(self):
        self.river_parent.phone = "212-555-0100"
        self.river_parent.save()
        source = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )

        shortcut = DialShortcut.objects.create(
            source_device=source,
            digits="2",
            parent_phone_target=self.river_parent,
            approved_by=self.river_parent,
        )

        self.assertEqual(shortcut.parent_phone_target.phone, "+12125550100")

    def test_dial_shortcut_can_target_same_family_child_landline(self):
        source = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        landline = ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.river_parent,
        )

        shortcut = DialShortcut.objects.create(
            source_device=source,
            digits="2",
            child_landline_target=landline,
            approved_by=self.river_parent,
        )

        self.assertEqual(shortcut.child_landline_target, landline)

    def test_dial_shortcut_can_target_childs_dialable_conference_group(self):
        source = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )
        group = ConferenceGroup.objects.create(
            name="Friends",
            calling_enabled=True,
            dial_extension="4444",
        )
        group.members.set([self.alex, self.emma])

        shortcut = DialShortcut.objects.create(
            source_device=source,
            digits="3",
            conference_group_target=group,
            approved_by=self.river_parent,
        )

        self.assertEqual(shortcut.conference_group_target, group)

    def test_dial_shortcut_rejects_conference_group_for_nonmember(self):
        source = Device.objects.create(
            assigned_child=self.luca,
            friendly_name="Luca bedroom phone",
            sip_extension="103",
            sip_username="luca-103",
            sip_secret="secret-l",
        )
        group = ConferenceGroup.objects.create(
            name="Friends",
            calling_enabled=True,
            dial_extension="4444",
        )
        group.members.set([self.alex, self.emma])

        with self.assertRaisesMessage(
            ValidationError,
            "Source device's child must be a member of this conference group.",
        ):
            DialShortcut.objects.create(
                source_device=source,
                digits="3",
                conference_group_target=group,
                approved_by=self.maple_parent,
            )

    def test_dial_shortcut_rejects_conference_group_that_is_not_dialable(self):
        source = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )
        group = ConferenceGroup.objects.create(name="Friends")
        group.members.set([self.alex, self.emma])

        with self.assertRaisesMessage(
            ValidationError,
            "Conference group must be active and dialable.",
        ):
            DialShortcut.objects.create(
                source_device=source,
                digits="3",
                conference_group_target=group,
                approved_by=self.river_parent,
            )

    def test_dial_shortcut_rejects_unapproved_child_landline(self):
        source = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        landline = ChildLandline.objects.create(
            child=self.emma,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.maple_parent,
        )

        with self.assertRaises(ValidationError):
            DialShortcut.objects.create(
                source_device=source,
                digits="2",
                child_landline_target=landline,
                approved_by=self.river_parent,
            )

    def test_dial_shortcut_rejects_inactive_child_landline(self):
        source = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("+1 212 555 0100")
        landline = ChildLandline.objects.create(
            child=self.alex,
            external_phone_number=number,
            dial_extension="2222",
            approved_by=self.river_parent,
            is_active=False,
        )

        with self.assertRaises(ValidationError):
            DialShortcut.objects.create(
                source_device=source,
                digits="2",
                child_landline_target=landline,
                approved_by=self.river_parent,
            )

    def test_dial_shortcut_rejects_parent_phone_from_other_family(self):
        self.maple_parent.phone = "212-555-0100"
        self.maple_parent.save()
        source = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )

        with self.assertRaises(ValidationError):
            DialShortcut.objects.create(
                source_device=source,
                digits="2",
                parent_phone_target=self.maple_parent,
                approved_by=self.river_parent,
            )

    def test_dial_shortcut_rejects_parent_without_phone(self):
        source = Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="101",
            sip_username="alex-101",
            sip_secret="secret-a",
        )

        with self.assertRaises(ValidationError):
            DialShortcut.objects.create(
                source_device=source,
                digits="2",
                parent_phone_target=self.river_parent,
                approved_by=self.river_parent,
            )

    def test_child_family_relationship_requires_both_approvals_to_be_active(self):
        relationship = AllowedChildFamilyRelationship.objects.create(
            child=self.alex,
            target_family=self.family_b,
            approved_by_child_family_guardian=self.river_parent,
        )

        self.assertFalse(relationship.is_active)

        relationship.approved_by_target_family_guardian = self.maple_parent
        relationship.save()

        self.assertTrue(relationship.is_active)

    def test_child_family_relationship_rejects_same_family_target(self):
        relationship = AllowedChildFamilyRelationship(
            child=self.alex,
            target_family=self.family_a,
            approved_by_child_family_guardian=self.river_parent,
            approved_by_target_family_guardian=self.river_parent,
        )

        with self.assertRaises(ValidationError):
            relationship.full_clean()

    def test_child_family_relationship_rejects_wrong_family_guardians(self):
        wrong_child_family_approval = AllowedChildFamilyRelationship(
            child=self.alex,
            target_family=self.family_b,
            approved_by_child_family_guardian=self.maple_parent,
            approved_by_target_family_guardian=self.maple_parent,
        )
        wrong_target_family_approval = AllowedChildFamilyRelationship(
            child=self.alex,
            target_family=self.family_b,
            approved_by_child_family_guardian=self.river_parent,
            approved_by_target_family_guardian=self.river_parent,
        )

        with self.assertRaises(ValidationError):
            wrong_child_family_approval.full_clean()
        with self.assertRaises(ValidationError):
            wrong_target_family_approval.full_clean()

    def test_child_family_relationship_is_unique_per_child_and_target_family(self):
        AllowedChildFamilyRelationship.objects.create(
            child=self.alex,
            target_family=self.family_b,
            approved_by_child_family_guardian=self.river_parent,
            approved_by_target_family_guardian=self.maple_parent,
        )
        duplicate = AllowedChildFamilyRelationship(
            child=self.alex,
            target_family=self.family_b,
            approved_by_child_family_guardian=self.river_parent,
            approved_by_target_family_guardian=self.maple_parent,
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_conference_requires_explicit_active_group(self):
        group = ConferenceGroup.objects.create(name="Saturday cousins", is_active=False)
        group.members.set([self.alex, self.emma, self.luca])

        self.assertFalse(children_may_conference([self.alex, self.emma, self.luca]))

        group.is_active = True
        group.save()

        self.assertTrue(children_may_conference([self.alex, self.emma, self.luca]))

    def test_conference_calling_assigns_unused_four_digit_extension(self):
        group = ConferenceGroup.objects.create(
            name="Saturday cousins",
            calling_enabled=True,
        )

        self.assertEqual(len(group.dial_extension), 4)
        self.assertTrue(group.dial_extension.isdigit())
        self.assertEqual(group.ring_timeout_seconds, 30)

    def test_disabled_conference_group_does_not_assign_extension(self):
        group = ConferenceGroup.objects.create(name="Saturday cousins")

        self.assertIsNone(group.dial_extension)

    def test_conference_extension_rejects_device_collision(self):
        Device.objects.create(
            assigned_child=self.alex,
            friendly_name="Alex bedroom phone",
            sip_extension="4444",
            sip_username="alex-4444",
            sip_secret="secret",
        )

        with self.assertRaisesMessage(
            ValidationError,
            "This extension is already assigned to a device.",
        ):
            ConferenceGroup.objects.create(
                name="Saturday cousins",
                calling_enabled=True,
                dial_extension="4444",
            )

    def test_device_rejects_conference_extension_collision(self):
        ConferenceGroup.objects.create(
            name="Saturday cousins",
            calling_enabled=True,
            dial_extension="4444",
        )

        with self.assertRaisesMessage(
            ValidationError,
            "This extension is already assigned to a conference group.",
        ):
            Device.objects.create(
                assigned_child=self.alex,
                friendly_name="Alex bedroom phone",
                sip_extension="4444",
                sip_username="alex-4444",
                sip_secret="secret",
            )

    def test_conference_ring_timeout_is_bounded(self):
        with self.assertRaises(ValidationError):
            ConferenceGroup.objects.create(
                name="Saturday cousins",
                ring_timeout_seconds=4,
            )
