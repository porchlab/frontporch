from datetime import time
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from directory.asterisk.domain import BlackoutWindow
from directory.asterisk.builder import build_asterisk_configuration
from directory.forms import ChildBlackoutPeriodForm, FamilySettingsForm
from directory.models import Child, ChildBlackoutPeriod, Family, FamilyActivity, Parent
from directory.tests.factories import create_user


class FamilyTimezoneTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Maple", timezone="America/Los_Angeles")
        self.other_family = Family.objects.create(name="River", timezone="Europe/London")
        self.parent = Parent.objects.create(
            user=create_user(), family=self.family, display_name="Morgan"
        )
        self.child = Child.objects.create(family=self.family, name="Alex")
        self.period = ChildBlackoutPeriod.objects.create(
            child=self.child, label="Bedtime", day_group="weekdays",
            start_time=time(20), end_time=time(7, 15), approved_by=self.parent,
        )
        self.client.force_login(self.parent.user)

    def test_existing_family_default_is_eastern(self):
        self.assertEqual(Family.objects.create(name="Oak").timezone, "America/New_York")

    def test_invalid_and_injected_zones_are_rejected_before_rendering(self):
        for name in ("Mars/Olympus", "localtime", "../etc/passwd", "UTC?bad,s,1", ""):
            with self.subTest(timezone=name):
                with self.assertRaises(ValidationError):
                    Family.objects.create(name="Invalid", timezone=name)
                with self.assertRaises(ValidationError):
                    BlackoutWindow(time_range="20:00-23:59", days="mon-fri", timezone=name)
                form = FamilySettingsForm(
                    {"name": self.family.name, "timezone": name}, instance=self.family
                )
                self.assertFalse(form.is_valid())
                self.assertIn("timezone", form.errors)

    def test_quiet_hours_pages_display_family_zone_independent_of_server(self):
        with override_settings(TIME_ZONE="UTC"):
            response = self.client.get(reverse("directory:child_detail", args=[self.child.pk]))
            self.assertContains(response, "America/Los_Angeles, your family’s time zone")
            form = ChildBlackoutPeriodForm(child=self.child, approved_by=self.parent)
            self.assertIn("America/Los_Angeles", form.fields["start_time"].help_text)
            self.assertNotIn("UTC", form.fields["start_time"].help_text)

    def test_raw_invalid_stored_timezone_cannot_generate_phone_config(self):
        # Even writes that bypass model validation must fail closed at rendering.
        Family.objects.filter(pk=self.family.pk).update(timezone="UTC?bad,s,1")
        with self.assertRaises(ValidationError):
            build_asterisk_configuration()

    @override_settings(ASTERISK_AUTO_APPLY_CONFIG=True)
    def test_zone_change_keeps_local_times_is_audited_and_reloads_config(self):
        with patch("directory.asterisk.autoreload.apply_asterisk_configuration") as apply:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("directory:settings"), {
                    "form": "family", "name": self.family.name,
                    "timezone": "Pacific/Auckland", "family_id": self.other_family.pk,
                })
            self.assertRedirects(response, reverse("directory:settings"))
            apply.assert_called_once_with(reload=True)
        self.family.refresh_from_db()
        self.other_family.refresh_from_db()
        self.period.refresh_from_db()
        self.assertEqual(self.family.timezone, "Pacific/Auckland")
        self.assertEqual(self.other_family.timezone, "Europe/London")
        self.assertEqual((self.period.start_time, self.period.end_time), (time(20), time(7, 15)))
        self.assertTrue(FamilyActivity.objects.filter(
            family=self.family, actor=self.parent.user,
            description__contains="Quiet hours use Pacific/Auckland",
        ).exists())

    def test_non_guardian_cannot_change_timezone(self):
        self.parent.is_guardian = False
        self.parent.save()
        response = self.client.post(reverse("directory:settings"), {
            "form": "family", "name": self.family.name, "timezone": "UTC",
        })
        self.assertEqual(response.status_code, 403)
        self.family.refresh_from_db()
        self.assertEqual(self.family.timezone, "America/Los_Angeles")


class FamilyTimezoneMigrationTests(TransactionTestCase):
    @override_settings(TIME_ZONE="UTC")
    def test_upgrade_preserves_existing_local_schedules(self):
        before = ("directory", "0023_groupinvitation")
        after = ("directory", "0024_family_timezone")
        executor = MigrationExecutor(connection)
        executor.migrate([before])
        try:
            apps = executor.loader.project_state([before]).apps
            family = apps.get_model("directory", "Family").objects.create(name="Oak")
            parent = apps.get_model("directory", "Parent").objects.create(
                family=family, user_id=create_user().pk, display_name="Taylor", dial_extension="3101",
            )
            child = apps.get_model("directory", "Child").objects.create(family=family, name="Casey")
            Period = apps.get_model("directory", "ChildBlackoutPeriod")
            Period.objects.create(
                child=child, label="Bedtime", day_group="weekdays",
                start_time=time(20), end_time=time(7, 15), approved_by=parent,
            )
            saved_schedules = list(Period.objects.values())
            MigrationExecutor(connection).migrate([after])
            self.assertEqual(Family.objects.get(pk=family.pk).timezone, "America/New_York")
            self.assertEqual(list(ChildBlackoutPeriod.objects.values()), saved_schedules)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
