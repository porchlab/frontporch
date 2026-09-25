from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from directory.asterisk.builder import build_asterisk_configuration
from directory.models import (
    Child,
    ChildConnection,
    ConnectionInvitation,
    Device,
    Family,
    Parent,
)
from directory.tests.factories import create_user


class LegacyRelationshipRemovalTests(TransactionTestCase):
    def test_removal_preserves_current_permissions_without_replaying_old_approvals(self):
        before = ("directory", "0021_unified_parent_calling")
        after = ("directory", "0022_remove_legacy_family_relationships")
        executor = MigrationExecutor(connection)
        executor.migrate([before])
        try:
            old_apps = executor.loader.project_state([before]).apps
            Relationship = old_apps.get_model(
                "directory", "AllowedChildFamilyRelationship"
            )
            first = Family.objects.create(name="Maple removal")
            second = Family.objects.create(name="Willow removal")
            first_parent = Parent.objects.create(
                family=first,
                user=create_user(),
                display_name="Taylor",
                dial_extension="201",
            )
            second_parent = Parent.objects.create(
                family=second,
                user=create_user(),
                display_name="Morgan",
                dial_extension="202",
            )
            a = Child.objects.create(family=first, name="Casey")
            b = Child.objects.create(family=second, name="Alex")
            c = Child.objects.create(family=second, name="Jamie")
            pending = Child.objects.create(family=first, name="Riley")
            # Old reciprocal rows remain approved even though a current pair was
            # revoked and a second pair was removed entirely after migration 0017.
            for child, target, guardian, target_guardian in (
                (a, second, first_parent, second_parent),
                (b, first, second_parent, first_parent),
                (c, first, second_parent, first_parent),
                (pending, second, first_parent, second_parent),
            ):
                Relationship.objects.create(
                    child_id=child.pk,
                    target_family_id=target.pk,
                    approved_by_child_family_guardian_id=guardian.pk,
                    approved_by_target_family_guardian_id=target_guardian.pk,
                    notes="Historical approval only.",
                )
            for child, active in ((b, True), (c, False)):
                ChildConnection.objects.create(
                    child_a=a,
                    child_b=child,
                    approved_by_a=first_parent,
                    approved_by_b=second_parent,
                    is_active=active,
                )
            invitation = ConnectionInvitation.objects.create(
                source_family=first,
                target_family=second,
                sent_by=first_parent,
                message="New request still waiting for approval.",
            )
            invitation.source_children.add(pending)
            for child, extension in (
                (a, "3101"), (b, "3102"), (c, "3103"), (pending, "3104")
            ):
                Device.objects.create(
                    assigned_child=child,
                    friendly_name=f"{child.name}'s phone",
                    sip_extension=extension,
                    sip_username=f"child-{extension}",
                    sip_secret="test-only-secret",
                )
            pairs_before = list(ChildConnection.objects.order_by("pk").values())
            invitations_before = list(
                ConnectionInvitation.objects.order_by("pk").values()
            )
            configuration_before = build_asterisk_configuration()

            executor = MigrationExecutor(connection)
            executor.migrate([after])

            self.assertEqual(
                list(ChildConnection.objects.order_by("pk").values()), pairs_before
            )
            self.assertEqual(
                list(ConnectionInvitation.objects.order_by("pk").values()),
                invitations_before,
            )
            self.assertEqual(list(invitation.source_children.all()), [pending])
            self.assertFalse(invitation.accepted_children.exists())
            self.assertEqual(build_asterisk_configuration(), configuration_before)
            self.assertNotIn(
                Relationship._meta.db_table, connection.introspection.table_names()
            )
            with self.assertRaises(LookupError):
                executor.loader.project_state([after]).apps.get_model(
                    "directory", "AllowedChildFamilyRelationship"
                )
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
