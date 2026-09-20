from django.contrib.auth.hashers import check_password, is_password_usable
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class GuardianAccountMigrationTests(TransactionTestCase):
    before = ("directory", "0019_family_invitations")
    after = ("directory", "0020_guardian_accounts")

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.before])
        self.apps = executor.loader.project_state([self.before]).apps
        self.Parent = self.apps.get_model("directory", "Parent")
        self.User = self.apps.get_model("auth", "User")
        self.family = self.apps.get_model("directory", "Family").objects.create(
            name="Maple upgrade"
        )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrate(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.after])
        return executor.loader.project_state([self.after]).apps

    def test_backfill_preserves_existing_accounts_and_relationships(self):
        from django.contrib.auth.hashers import make_password

        password = make_password("existing-password-123")
        existing = self.User.objects.create(
            username="existing", email="", password=password
        )
        linked = self.Parent.objects.create(
            family=self.family,
            display_name="Taylor",
            user=existing,
            email="TAYLOR@example.com",
            is_primary=True,
        )
        unlinked = self.Parent.objects.create(
            family=self.family, display_name="Morgan", email="MORGAN@example.com"
        )
        missing_email = self.Parent.objects.create(
            family=self.family, display_name="Sam"
        )
        removed = self.Parent.objects.create(
            family=self.family, display_name="Quinn", is_guardian=False
        )
        child = self.apps.get_model("directory", "Child").objects.create(
            family=self.family, name="Casey"
        )
        apps = self.migrate()
        Parent = apps.get_model("directory", "Parent")
        User = apps.get_model("auth", "User")
        EmailAddress = apps.get_model("account", "EmailAddress")
        self.assertEqual(Parent.objects.count(), 4)
        self.assertEqual(User.objects.count(), 4)
        self.assertFalse(Parent.objects.filter(user=None).exists())
        linked_after = Parent.objects.get(pk=linked.pk)
        self.assertEqual(linked_after.user_id, existing.pk)
        self.assertEqual(linked_after.user.password, password)
        self.assertTrue(linked_after.is_primary)
        self.assertEqual(linked_after.user.email, "taylor@example.com")
        hashes = set()
        for original in (unlinked, missing_email, removed):
            parent = Parent.objects.get(pk=original.pk)
            self.assertEqual(parent.family_id, self.family.pk)
            self.assertEqual(parent.is_guardian, original.is_guardian)
            self.assertTrue(parent.user.is_active)
            self.assertFalse(parent.user.is_staff)
            self.assertFalse(parent.user.is_superuser)
            self.assertTrue(parent.user.username.startswith("guardian_"))
            self.assertTrue(is_password_usable(parent.user.password))
            self.assertFalse(check_password("", parent.user.password))
            hashes.add(parent.user.password)
        self.assertEqual(len(hashes), 3)
        self.assertEqual(Parent.objects.get(pk=missing_email.pk).user.email, "")
        self.assertEqual(EmailAddress.objects.count(), 2)
        self.assertFalse(EmailAddress.objects.filter(verified=True).exists())
        self.assertEqual(
            apps.get_model("directory", "Child").objects.get(pk=child.pk).family_id,
            self.family.pk,
        )

        # Downgrade restores the old email column but never erases accounts.
        executor = MigrationExecutor(connection)
        executor.migrate([self.before])
        linked.refresh_from_db()
        self.assertEqual(linked.email, "taylor@example.com")
        self.assertEqual(self.User.objects.count(), 4)
        self.migrate()
        self.assertEqual(self.User.objects.count(), 4)

    def test_duplicate_email_aborts_without_silently_linking_an_existing_user(self):
        existing = self.User.objects.create(
            username="existing", email="morgan@example.com"
        )
        parent = self.Parent.objects.create(
            family=self.family, display_name="Morgan", email="MORGAN@example.com"
        )
        try:
            with self.assertRaisesMessage(RuntimeError, "Duplicate account email"):
                self.migrate()
            parent.refresh_from_db()
            self.assertIsNone(parent.user_id)
            self.assertEqual(self.User.objects.count(), 1)
        finally:
            # Explicit operator resolution makes a later retry safe.
            parent.user = existing
            parent.save(update_fields=["user"])

    def test_conflicting_linked_emails_abort_before_removing_contact_email(self):
        existing = self.User.objects.create(
            username="existing", email="login@example.com"
        )
        parent = self.Parent.objects.create(
            family=self.family,
            display_name="Taylor",
            email="contact@example.com",
            user=existing,
        )
        try:
            with self.assertRaisesMessage(RuntimeError, "have different emails"):
                self.migrate()
            parent.refresh_from_db()
            self.assertEqual(parent.email, "contact@example.com")
        finally:
            parent.email = existing.email
            parent.save(update_fields=["email"])
