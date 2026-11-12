from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ChildShortcutMigrationTests(TransactionTestCase):
    before = ("directory", "0028_phone_deregistration")
    after = ("directory", "0029_child_owned_shortcuts")

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.before])
        apps = executor.loader.project_state([self.before]).apps
        self.Shortcut = apps.get_model("directory", "DialShortcut")
        self.Device = apps.get_model("directory", "Device")
        family = apps.get_model("directory", "Family").objects.create(
            name="Maple upgrade"
        )
        user = apps.get_model("auth", "User").objects.create(
            username="fictional-upgrade-parent"
        )
        self.parent = apps.get_model("directory", "Parent").objects.create(
            family=family, user=user, display_name="Morgan", dial_extension="5000"
        )
        self.child = apps.get_model("directory", "Child").objects.create(
            family=family, name="Casey"
        )
        self.peer = apps.get_model("directory", "Child").objects.create(
            family=family, name="Alex"
        )
        self.source = self.device(self.child, "5101")
        self.target = self.device(self.peer, "5102")

    def tearDown(self):
        # Remove rows through a schema-independent queryset before restoring the
        # current schema, including after the intentional failed upgrade.
        self.Shortcut.objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def device(self, child, extension):
        return self.Device.objects.create(
            assigned_child=child,
            friendly_name="Fictional phone",
            sip_extension=extension,
            sip_username=f"fictional-{extension}",
            sip_secret="fictional-secret",
        )

    def test_upgrade_keeps_ids_metadata_approvals_paused_and_unapproved_rows(self):
        rows = []
        for digits, active, approver in (
            ("1", True, self.parent),
            ("2", False, self.parent),
            ("3", True, None),
        ):
            rows.append(
                self.Shortcut.objects.create(
                    source_device=self.source,
                    internal_target_device=self.target,
                    digits=digits,
                    is_active=active,
                    approved_by=approver,
                    label=f"Key {digits}",
                    notes="Preserve this note",
                )
            )
        shared = self.Device.objects.create(
            assigned_family=self.parent.family,
            friendly_name="Shared phone",
            sip_extension="5103",
            sip_username="fictional-shared",
            sip_secret="fictional-secret",
        )
        incoming = self.Shortcut.objects.create(
            source_device=shared,
            digits="4",
            internal_target_device=self.source,
            approved_by=self.parent,
        )
        executor = MigrationExecutor(connection)
        executor.migrate([self.after])
        apps = executor.loader.project_state([self.after]).apps
        Shortcut = apps.get_model("directory", "DialShortcut")
        for old in rows:
            new = Shortcut.objects.get(pk=old.pk)
            self.assertEqual(
                (new.source_child_id, new.child_target_id),
                (self.child.pk, self.peer.pk),
            )
            self.assertIsNone(new.source_device_id)
            self.assertIsNone(new.internal_target_device_id)
            for field in (
                "digits",
                "label",
                "notes",
                "is_active",
                "approved_by_id",
                "created_at",
                "updated_at",
            ):
                self.assertEqual(getattr(new, field), getattr(old, field))
        new = Shortcut.objects.get(pk=incoming.pk)
        self.assertEqual(
            (new.source_device_id, new.child_target_id), (shared.pk, self.child.pk)
        )
        activity = apps.get_model("directory", "FamilyActivity").objects.get()
        self.assertEqual(len(activity.details["previous_device_references"]), 4)
        apps.get_model("directory", "Device").objects.filter(
            pk__in=[self.source.pk, self.target.pk]
        ).delete()
        self.assertEqual(Shortcut.objects.count(), 4)

    def test_duplicate_child_keys_abort_atomically_without_selecting_a_winner(self):
        other = self.device(self.child, "5103")
        for source in (self.source, other):
            self.Shortcut.objects.create(
                source_device=source,
                digits="1",
                internal_target_device=self.target,
                approved_by=self.parent,
            )
        with self.assertRaisesMessage(
            RuntimeError, "multiple phones belonging to one child"
        ):
            MigrationExecutor(connection).migrate([self.after])
        self.assertEqual(
            set(self.Shortcut.objects.values_list("source_device_id", flat=True)),
            {self.source.pk, other.pk},
        )
        self.assertEqual(
            set(
                self.Shortcut.objects.values_list(
                    "internal_target_device_id", flat=True
                )
            ),
            {self.target.pk},
        )
