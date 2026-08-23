from unittest.mock import patch

from django.db import transaction
from django.test import TransactionTestCase, override_settings

from directory.models import (
    Child,
    ChildLandline,
    ChildLandlineDialShortcut,
    ConferenceGroup,
    Device,
    ExternalNumberExtension,
    ExternalPhoneNumber,
    Family,
    FamilyContact,
    Parent,
)


class AsteriskAutoReloadSignalTests(TransactionTestCase):
    @override_settings(ASTERISK_AUTO_APPLY_CONFIG=True)
    @patch("directory.asterisk.autoreload.apply_asterisk_configuration")
    def test_asterisk_affecting_create_applies_configuration_after_commit(self, apply):
        Family.objects.create(name="River House")

        apply.assert_called_once_with(reload=True)

    @override_settings(ASTERISK_AUTO_APPLY_CONFIG=True)
    @patch("directory.asterisk.autoreload.apply_asterisk_configuration")
    def test_asterisk_affecting_delete_applies_configuration_after_commit(self, apply):
        with override_settings(ASTERISK_AUTO_APPLY_CONFIG=False):
            family = Family.objects.create(name="River House")

        family.delete()

        apply.assert_called_once_with(reload=True)

    @override_settings(ASTERISK_AUTO_APPLY_CONFIG=True)
    @patch("directory.asterisk.autoreload.apply_asterisk_configuration")
    def test_rolled_back_change_does_not_apply_configuration(self, apply):
        try:
            with transaction.atomic():
                Family.objects.create(name="Rolled Back House")
                raise RuntimeError("rollback")
        except RuntimeError:
            pass

        apply.assert_not_called()

    @override_settings(ASTERISK_AUTO_APPLY_CONFIG=True)
    @patch("directory.asterisk.autoreload.apply_asterisk_configuration")
    def test_family_contact_create_applies_configuration(self, apply):
        with override_settings(ASTERISK_AUTO_APPLY_CONFIG=False):
            family = Family.objects.create(name="River House")
            number = ExternalPhoneNumber.objects.create(normalized_number="+12125550100")
            ExternalNumberExtension.objects.create(
                external_phone_number=number,
                dial_extension="2222",
            )

        FamilyContact.objects.create(
            family=family,
            external_phone_number=number,
            label="Grandparent",
        )

        apply.assert_called_once_with(reload=True)

    @override_settings(ASTERISK_AUTO_APPLY_CONFIG=True)
    @patch("directory.asterisk.autoreload.apply_asterisk_configuration")
    def test_conference_save_and_membership_change_coalesce_after_commit(self, apply):
        with override_settings(ASTERISK_AUTO_APPLY_CONFIG=False):
            family = Family.objects.create(name="River House")
            alex = Child.objects.create(family=family, name="Alex")
            emma = Child.objects.create(family=family, name="Emma")

        with transaction.atomic():
            group = ConferenceGroup.objects.create(
                name="Friends",
                calling_enabled=True,
            )
            group.members.set([alex, emma])

        apply.assert_called_once_with(reload=True)

    @override_settings(ASTERISK_AUTO_APPLY_CONFIG=True)
    @patch("directory.asterisk.autoreload.apply_asterisk_configuration")
    def test_child_landline_shortcut_save_and_delete_apply_configuration(self, apply):
        with override_settings(ASTERISK_AUTO_APPLY_CONFIG=False):
            family = Family.objects.create(name="River House")
            parent = Parent.objects.create(family=family, display_name="Mara")
            source_child = Child.objects.create(family=family, name="Riley")
            target_child = Child.objects.create(family=family, name="Rowan")
            Device.objects.create(
                assigned_child=target_child,
                friendly_name="Rowan bedroom phone",
                sip_extension="3552",
                sip_username="rowan-3552",
                sip_secret="secret-rowan",
            )
            number = ExternalPhoneNumber.objects.create(
                normalized_number="+12125550100"
            )
            source = ChildLandline.objects.create(
                child=source_child,
                external_phone_number=number,
                approved_by=parent,
            )

        shortcut = ChildLandlineDialShortcut.objects.create(
            source_landline=source,
            digits="2",
            target_child=target_child,
            approved_by=parent,
        )

        apply.assert_called_once_with(reload=True)
        apply.reset_mock()

        shortcut.delete()

        apply.assert_called_once_with(reload=True)

    @override_settings(ASTERISK_AUTO_APPLY_CONFIG=True)
    @patch("directory.asterisk.autoreload.apply_asterisk_configuration")
    def test_child_landline_change_applies_configuration_and_private_prompts(
        self,
        apply,
    ):
        with override_settings(ASTERISK_AUTO_APPLY_CONFIG=False):
            family = Family.objects.create(name="Maple House")
            parent = Parent.objects.create(family=family, display_name="Nico")
            child = Child.objects.create(family=family, name="Rowan")
            number = ExternalPhoneNumber.objects.create(
                normalized_number="+12125550100"
            )
            landline = ChildLandline.objects.create(
                child=child,
                external_phone_number=number,
                approved_by=parent,
            )

        landline.is_active = False
        landline.save()

        apply.assert_called_once_with(reload=True)

    @override_settings(ASTERISK_AUTO_APPLY_CONFIG=True)
    @patch("directory.asterisk.autoreload.apply_asterisk_configuration")
    def test_child_spoken_name_change_applies_configuration_and_prompts(self, apply):
        with override_settings(ASTERISK_AUTO_APPLY_CONFIG=False):
            family = Family.objects.create(name="River House")
            child = Child.objects.create(family=family, name="Alex")

        child.spoken_name = "AL-eks"
        child.save()

        apply.assert_called_once_with(reload=True)
