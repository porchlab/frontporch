from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ParentCallingUpgradeTests(TransactionTestCase):
    before = ("directory", "0020_guardian_accounts")
    after = ("directory", "0021_unified_parent_calling")

    def test_existing_numbers_shortcuts_approvals_and_activation_are_preserved(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.before])
        try:
            apps = executor.loader.project_state([self.before]).apps
            Family, Parent, Child, Device, Shortcut = [
                apps.get_model("directory", name)
                for name in ("Family", "Parent", "Child", "Device", "DialShortcut")
            ]
            User = apps.get_model("auth", "User")
            family = Family.objects.create(name="Maple upgrade")
            remote = Family.objects.create(name="Willow upgrade")

            def parent(name, phone="", owner=family):
                return Parent.objects.create(
                    family=owner,
                    display_name=name,
                    phone=phone,
                    user=User.objects.create(username=f"fictional-{name}"),
                )

            taylor = parent("Taylor", "+12025550188")
            mobile = parent("Morgan", "+12025550187")
            unconfigured = parent("Rowan", "+12025550186")
            foreign = parent("Avery", "+12025550185", remote)
            child = Child.objects.create(family=family, name="Casey")
            source = Device.objects.create(
                assigned_child=child,
                friendly_name="Bedroom",
                sip_extension="5001",
                sip_username="fictional-child",
                sip_secret="fictional-child-secret",
            )

            def device(extension, active):
                return Device.objects.create(
                    assigned_parent=taylor,
                    friendly_name=f"Desk {extension}",
                    sip_extension=extension,
                    sip_username=f"fictional-{extension}",
                    sip_secret="fictional-device-secret",
                    is_active=active,
                )

            inactive = device("5004", False)
            desk = device("5002", True)
            app = device("5003", True)
            old = []
            for digits, target, active, approver in [
                ("1", {"parent_phone_target": taylor}, True, taylor),
                ("2", {"internal_target_device": desk}, True, taylor),
                ("3", {"internal_target_device": inactive}, False, taylor),
                ("4", {"parent_phone_target": mobile}, True, taylor),
                ("5", {"parent_phone_target": unconfigured}, False, taylor),
                ("6", {"parent_phone_target": unconfigured}, True, None),
                ("7", {"parent_phone_target": unconfigured}, True, foreign),
                ("8", {"parent_phone_target": foreign}, True, taylor),
            ]:
                old.append(
                    Shortcut.objects.create(
                        source_device=source,
                        digits=digits,
                        label=f"Key {digits}",
                        notes="Keep this note",
                        is_active=active,
                        approved_by=approver,
                        **target,
                    )
                )
            executor = MigrationExecutor(connection)
            executor.migrate([self.after])
            apps = executor.loader.project_state([self.after]).apps
            Parent, Device, Shortcut, Activity = [
                apps.get_model("directory", name)
                for name in ("Parent", "Device", "DialShortcut", "FamilyActivity")
            ]
            upgraded = Parent.objects.get(pk=taylor.pk)
            self.assertEqual(
                (upgraded.dial_extension, upgraded.call_destination), ("5002", "both")
            )
            upgraded_mobile = Parent.objects.get(pk=mobile.pk)
            self.assertEqual(upgraded_mobile.call_destination, "phone")
            self.assertEqual(len(upgraded_mobile.dial_extension), 4)
            self.assertEqual(
                Parent.objects.get(pk=unconfigured.pk).call_destination, "frontporch"
            )
            self.assertEqual(
                Parent.objects.get(pk=foreign.pk).call_destination, "frontporch"
            )
            numbers = list(Parent.objects.values_list("dial_extension", flat=True))
            self.assertEqual(len(numbers), len(set(numbers)))
            self.assertNotIn("5001", numbers)
            for previous in (desk, app, inactive):
                current = Device.objects.get(pk=previous.pk)
                self.assertEqual(current.sip_extension, "5002")
                self.assertEqual(current.is_active, previous.is_active)
                self.assertEqual(current.sip_username, previous.sip_username)
                self.assertEqual(current.sip_secret, previous.sip_secret)
            for previous in old:
                current = Shortcut.objects.get(pk=previous.pk)
                self.assertEqual(current.source_device_id, previous.source_device_id)
                self.assertEqual(current.digits, previous.digits)
                self.assertEqual(current.label, previous.label)
                self.assertEqual(current.notes, previous.notes)
                self.assertEqual(current.is_active, previous.is_active)
                self.assertEqual(current.approved_by_id, previous.approved_by_id)
                self.assertIsNone(current.internal_target_device_id)
            self.assertEqual(
                Shortcut.objects.get(digits="2").parent_target_id, taylor.pk
            )
            self.assertEqual(
                Activity.objects.filter(
                    description__startswith="Unified calling"
                ).count(),
                4,
            )
            self.assertFalse(
                Activity.objects.filter(description__contains="+1202555").exists()
            )
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
