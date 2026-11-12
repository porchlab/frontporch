from datetime import time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from directory import models as m
from directory.asterisk.builder import build_asterisk_configuration
from directory.phonebook import device_phonebook
from directory.services import shortcut_destinations
from directory.tests.factories import create_user


class ChildShortcutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.family = m.Family.objects.create(name="Maple")
        cls.remote = m.Family.objects.create(name="Willow")
        cls.parent = m.Parent.objects.create(
            family=cls.family, user=create_user(), display_name="Morgan"
        )
        cls.other = m.Parent.objects.create(
            family=cls.remote, user=create_user(), display_name="Taylor"
        )
        cls.child = m.Child.objects.create(family=cls.family, name="Casey")
        cls.peer = m.Child.objects.create(family=cls.remote, name="Alex")
        cls.sibling = m.Child.objects.create(family=cls.family, name="Robin")
        cls.pair = m.ChildConnection.objects.create(
            child_a=cls.child,
            child_b=cls.peer,
            approved_by_a=cls.parent,
            approved_by_b=cls.other,
        )

    def phone(self, child, extension):
        return m.Device.objects.create(
            assigned_child=child,
            friendly_name="Fictional phone",
            sip_extension=extension,
            sip_username=f"fictional-{extension}",
            sip_secret="fictional-secret",
        )

    def routes(self):
        return {
            (r.source_endpoint.device_id, r.digits, r.target_endpoint.device_id)
            for r in build_asterisk_configuration().shortcut_rules
            if r.target_endpoint
        }

    def test_replacing_both_handsets_preserves_incoming_and_outgoing_shortcuts(self):
        source, target = self.phone(self.child, "5101"), self.phone(self.peer, "5102")
        outgoing = m.DialShortcut.objects.create(
            source_device=source,
            internal_target_device=target,
            approved_by=self.parent,
            digits="2",
            label="Buddy",
            notes="Keep this note",
        )
        incoming = m.DialShortcut.objects.create(
            source_device=target,
            internal_target_device=source,
            approved_by=self.other,
            digits="3",
            label="Friend",
        )
        outgoing.refresh_from_db()
        self.assertEqual(
            (outgoing.source_child_id, outgoing.child_target_id),
            (self.child.pk, self.peer.pk),
        )
        self.assertIsNone(outgoing.source_device_id)
        self.assertIsNone(outgoing.internal_target_device_id)
        source.delete()
        target.delete()
        self.assertEqual(m.DialShortcut.objects.count(), 2)
        self.assertEqual(self.routes(), set())
        self.client.force_login(self.parent.user)
        self.assertContains(
            self.client.get(reverse("directory:child_shortcuts", args=[self.child.pk])),
            "Buddy",
        )
        source, target = self.phone(self.child, "5111"), self.phone(self.peer, "5112")
        self.assertEqual(
            self.routes(), {(source.pk, "2", target.pk), (target.pk, "3", source.pk)}
        )
        outgoing.refresh_from_db()
        self.assertEqual(
            (outgoing.label, outgoing.notes, outgoing.approved_by_id),
            ("Buddy", "Keep this note", self.parent.pk),
        )
        self.assertEqual(
            device_phonebook(source)[0].shortcuts, [{"digits": "2", "label": "Buddy"}]
        )
        self.assertTrue(m.DialShortcut.objects.filter(pk=incoming.pk).exists())

    def test_shared_keys_ring_all_active_child_phones_and_recheck_permissions(self):
        sources = [self.phone(self.child, n) for n in ("5101", "5102")]
        targets = [self.phone(self.peer, n) for n in ("5201", "5202")]
        excluded = self.phone(self.sibling, "5301")
        m.ChildBlackoutPeriod.objects.create(
            child=self.peer,
            label="Bedtime",
            day_group="weekdays",
            approved_by=self.other,
            start_time=time(20),
            end_time=time(7),
        )
        shortcut = m.DialShortcut.objects.create(
            source_child=self.child,
            child_target=self.peer,
            approved_by=self.parent,
            digits="1",
        )
        self.assertEqual(
            self.routes(), {(s.pk, "1", t.pk) for s in sources for t in targets}
        )
        for source in sources:
            book = {e.extension: e.shortcuts for e in device_phonebook(source)}
            for target in targets:
                self.assertEqual(
                    book[target.sip_extension], [{"digits": "1", "label": ""}]
                )
        self.assertFalse(
            any(
                r.source_endpoint.device_id == excluded.pk
                for r in build_asterisk_configuration().shortcut_rules
            )
        )
        self.assertTrue(
            all(
                r.target_endpoint.blackout_windows
                for r in build_asterisk_configuration().shortcut_rules
            )
        )
        targets[0].is_active = False
        targets[0].save()
        self.assertEqual(self.routes(), {(s.pk, "1", targets[1].pk) for s in sources})
        for changes in (
            {"approved_by": None},
            {"approved_by": self.other},
            {"is_active": False},
        ):
            m.DialShortcut.objects.filter(pk=shortcut.pk).update(**changes)
            self.assertEqual(self.routes(), set())
            m.DialShortcut.objects.filter(pk=shortcut.pk).update(
                approved_by=self.parent, is_active=True
            )
        self.pair.is_active = False
        self.pair.save()
        self.assertEqual(self.routes(), set())
        self.assertNotIn(f"child:{self.peer.pk}", shortcut_destinations(self.child))
        self.assertTrue(m.DialShortcut.objects.filter(pk=shortcut.pk).exists())

    def test_device_reassignment_does_not_move_source_keys_or_incoming_targets(self):
        source, target = self.phone(self.child, "5101"), self.phone(self.peer, "5102")
        shortcut = m.DialShortcut.objects.create(
            source_child=self.child,
            child_target=self.peer,
            approved_by=self.parent,
            digits="2",
        )
        source.assigned_child = self.sibling
        source.save()
        self.assertEqual(self.routes(), set())
        replacement = self.phone(self.child, "5103")
        self.assertEqual(self.routes(), {(replacement.pk, "2", target.pk)})
        target.assigned_child = self.sibling
        target.save()
        self.assertEqual(self.routes(), set())
        shortcut.refresh_from_db()
        self.assertEqual(shortcut.child_target_id, self.peer.pk)

    def test_child_portal_authorization_shared_uniqueness_and_no_phone_gap(self):
        self.phone(self.peer, "5102")
        self.client.force_login(self.parent.user)
        url = reverse("directory:child_shortcut_create", args=[self.child.pk])
        data = {"digits": "1", "target": f"child:{self.peer.pk}", "is_active": "on"}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        shortcut = self.child.dial_shortcuts.get()
        for phone in (self.phone(self.child, "5101"), self.phone(self.child, "5103")):
            response = self.client.post(
                reverse("directory:shortcut_create", args=[phone.pk]), data
            )
            self.assertContains(response, "This key is already assigned.")
        self.assertEqual(m.DialShortcut.objects.count(), 1)
        self.assertEqual(
            self.client.post(
                reverse("directory:child_shortcut_create", args=[self.sibling.pk]), data
            ).status_code,
            200,
        )
        self.assertFalse(self.sibling.dial_shortcuts.exists())  # No approved pair.
        self.client.force_login(self.other.user)
        for route, args in (
            ("child_shortcuts", [self.child.pk]),
            ("child_shortcut_create", [self.child.pk]),
            ("child_shortcut_edit", [self.child.pk, shortcut.pk]),
        ):
            url = reverse("directory:" + route, args=args)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, data).status_code, 404)
        for action in ("pause", "remove"):
            self.assertEqual(
                self.client.post(
                    reverse("directory:shortcut_action", args=[shortcut.pk, action])
                ).status_code,
                404,
            )
        shortcut.refresh_from_db()
        self.assertTrue(shortcut.is_active)
        self.assertEqual(m.FamilyActivity.objects.filter(family=self.family).count(), 1)

    def test_database_requires_exactly_one_source_target_and_unique_child_key(self):
        self.phone(self.peer, "5102")
        shortcut = m.DialShortcut.objects.create(
            source_child=self.child,
            child_target=self.peer,
            approved_by=self.parent,
            digits="1",
        )
        for values in ({"source_child": None}, {"child_target": None}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                m.DialShortcut.objects.filter(pk=shortcut.pk).update(**values)
        with self.assertRaises(ValidationError):
            m.DialShortcut.objects.create(
                source_child=self.child,
                child_target=self.peer,
                approved_by=self.parent,
                digits="1",
            )
        # Another child's key is independent, within existing family permissions.
        other = m.DialShortcut.objects.create(
            source_child=self.sibling,
            child_target=self.child,
            approved_by=self.parent,
            digits="1",
            is_active=False,
        )
        self.assertEqual(other.digits, shortcut.digits)
