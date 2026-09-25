from datetime import datetime, timezone

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
    FamilyActivity,
    Parent,
)
from directory.tests.factories import create_user


class LegacyRelationshipRemovalTests(TransactionTestCase):
    def test_rollback_keeps_archive_if_a_referenced_family_was_removed(self):
        before = ("directory", "0021_unified_parent_calling")
        after = ("directory", "0022_remove_legacy_family_relationships")
        executor = MigrationExecutor(connection)
        executor.migrate([before])
        try:
            Relationship = executor.loader.project_state([before]).apps.get_model(
                "directory", "AllowedChildFamilyRelationship"
            )
            first = Family.objects.create(name="Maple rollback")
            second = Family.objects.create(name="Willow rollback")
            child = Child.objects.create(family=first, name="Casey")
            Relationship.objects.create(
                child_id=child.pk,
                target_family_id=second.pk,
                notes="Unapproved historical request.",
            )
            MigrationExecutor(connection).migrate([after])
            archive_before = FamilyActivity.objects.get().details
            second.delete()

            with self.assertRaisesMessage(RuntimeError, "referenced people or families were removed"):
                MigrationExecutor(connection).migrate([before])

            self.assertEqual(FamilyActivity.objects.get().details, archive_before)
            self.assertNotIn(
                Relationship._meta.db_table, connection.introspection.table_names()
            )
            self.assertIn(after, MigrationExecutor(connection).loader.applied_migrations)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

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
            Activity = old_apps.get_model("directory", "FamilyActivity")
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
            old_activity = Activity.objects.create(
                family_id=first.pk, description="Earlier family activity."
            )
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
                    notes="Historical approval only.\n" * 50,
                )
            for name, source_guardian, target_guardian in (
                ("Awaiting", first_parent, None),
                ("Revoked", None, second_parent),
                ("Unapproved", None, None),
            ):
                child = Child.objects.create(family=first, name=name)
                Relationship.objects.create(
                    child_id=child.pk,
                    target_family_id=second.pk,
                    approved_by_child_family_guardian_id=(
                        source_guardian.pk if source_guardian else None
                    ),
                    approved_by_target_family_guardian_id=(
                        target_guardian.pk if target_guardian else None
                    ),
                    notes=f"Unconverted {name.lower()} approval.",
                )
            Relationship.objects.update(
                created_at=datetime(2020, 1, 2, tzinfo=timezone.utc),
                updated_at=datetime(2020, 2, 3, tzinfo=timezone.utc),
            )
            relationships_before = list(Relationship.objects.order_by("pk").values())
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
            archives = FamilyActivity.objects.exclude(pk=old_activity.pk)
            self.assertEqual(archives.count(), len(relationships_before))
            for original in relationships_before:
                archived = archives.get(details__id=original["id"])
                snapshot = archived.details
                child = Child.objects.get(pk=original["child_id"])
                target = Family.objects.get(pk=original["target_family_id"])
                self.assertEqual(archived.family_id, child.family_id)
                self.assertIsNone(archived.actor_id)
                self.assertEqual(archived.created_at, original["created_at"])
                self.assertEqual(archived.updated_at, original["updated_at"])
                self.assertEqual(snapshot["created_at"], original["created_at"].isoformat())
                self.assertEqual(snapshot["updated_at"], original["updated_at"].isoformat())
                self.assertEqual(snapshot["notes"], original["notes"])
                self.assertEqual(snapshot["child"], {
                    "id": child.pk, "name": child.name,
                    "family_id": child.family_id, "family_name": child.family.name,
                })
                self.assertEqual(snapshot["target_family"], {
                    "id": target.pk, "name": target.name,
                })
                for field in (
                    "approved_by_child_family_guardian",
                    "approved_by_target_family_guardian",
                ):
                    guardian_id = original[f"{field}_id"]
                    if guardian_id is None:
                        self.assertIsNone(snapshot[field])
                    else:
                        guardian = Parent.objects.get(pk=guardian_id)
                        self.assertEqual(snapshot[field], {
                            "id": guardian.pk,
                            "display_name": guardian.display_name,
                            "user_id": guardian.user_id,
                            "family_id": guardian.family_id,
                            "family_name": guardian.family.name,
                        })
            preserved_activity = FamilyActivity.objects.get(pk=old_activity.pk)
            self.assertEqual(preserved_activity.description, old_activity.description)
            self.assertEqual(preserved_activity.details, {})
            self.assertNotIn(
                Relationship._meta.db_table, connection.introspection.table_names()
            )
            with self.assertRaises(LookupError):
                executor.loader.project_state([after]).apps.get_model(
                    "directory", "AllowedChildFamilyRelationship"
                )

            # Rollback restores the full records, and another upgrade archives
            # them exactly once without changing present-day call permissions.
            executor = MigrationExecutor(connection)
            executor.migrate([before])
            self.assertEqual(
                list(Relationship.objects.order_by("pk").values()), relationships_before
            )
            self.assertEqual(Activity.objects.count(), 1)
            executor = MigrationExecutor(connection)
            executor.migrate([after])
            self.assertEqual(FamilyActivity.objects.count(), len(relationships_before) + 1)
            self.assertEqual(build_asterisk_configuration(), configuration_before)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
