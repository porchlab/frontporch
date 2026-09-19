from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PortalUpgradeTests(TransactionTestCase):
    def test_existing_data_gets_unique_codes_exact_pairs_and_pending_invitations(self):
        before = (
            "directory",
            "0015_remove_dialshortcut_dial_shortcut_has_exactly_one_target_and_more",
        )
        after = ("directory", "0018_guardianinvitation_parent_is_primary_and_more")
        executor = MigrationExecutor(connection)
        executor.migrate([before])
        try:
            apps = executor.loader.project_state([before]).apps
            Family, Parent, Child, Relationship = [
                apps.get_model("directory", name)
                for name in (
                    "Family",
                    "Parent",
                    "Child",
                    "AllowedChildFamilyRelationship",
                )
            ]
            first = Family.objects.create(name="Maple upgrade")
            second = Family.objects.create(name="Willow upgrade")
            first_parent = Parent.objects.create(family=first, display_name="Taylor")
            second_parent = Parent.objects.create(family=second, display_name="Morgan")
            a = Child.objects.create(family=first, name="Casey")
            b = Child.objects.create(family=second, name="Alex")
            pending = Child.objects.create(family=first, name="Riley")
            Child.objects.create(family=second, name="Jamie")
            Relationship.objects.create(
                child=a,
                target_family=second,
                approved_by_child_family_guardian=first_parent,
                approved_by_target_family_guardian=second_parent,
            )
            Relationship.objects.create(
                child=b,
                target_family=first,
                approved_by_child_family_guardian=second_parent,
                approved_by_target_family_guardian=first_parent,
            )
            Relationship.objects.create(
                child=pending,
                target_family=second,
                approved_by_child_family_guardian=first_parent,
            )
            executor = MigrationExecutor(connection)
            executor.migrate([after])
            apps = executor.loader.project_state([after]).apps
            Family, Parent, Pair, Invitation = [
                apps.get_model("directory", name)
                for name in (
                    "Family",
                    "Parent",
                    "ChildConnection",
                    "ConnectionInvitation",
                )
            ]
            codes = list(
                Family.objects.filter(pk__in=[first.pk, second.pk]).values_list(
                    "invite_code", flat=True
                )
            )
            self.assertEqual(len(set(codes)), 2)
            self.assertTrue(all(len(code) >= 24 for code in codes))
            self.assertFalse(Family.objects.filter(directory_listed=True).exists())
            self.assertEqual(
                set(Pair.objects.values_list("child_a_id", "child_b_id")),
                {(a.pk, b.pk)},
            )
            invitation = Invitation.objects.get(status="pending")
            self.assertEqual(
                list(invitation.source_children.values_list("pk", flat=True)),
                [pending.pk],
            )
            self.assertEqual(invitation.target_family_id, second.pk)
            self.assertTrue(Parent.objects.get(pk=first_parent.pk).is_primary)
            self.assertTrue(Parent.objects.get(pk=second_parent.pk).is_primary)
        finally:
            MigrationExecutor(connection).migrate([after])
