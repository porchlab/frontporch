from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.db import close_old_connections, connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from directory import models as m
from directory.asterisk.builder import build_asterisk_configuration
from directory.services import shortcut_destination_allowed


class GroupMembershipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.family = m.Family.objects.create(name="River", directory_listed=True)
        cls.other = m.Family.objects.create(name="Maple", directory_listed=True)
        cls.stranger = m.Family.objects.create(name="Cedar")
        cls.parent = m.Parent.objects.create(
            family=cls.family,
            display_name="Taylor",
            user=User.objects.create_user("taylor"),
        )
        cls.recipient = m.Parent.objects.create(
            family=cls.other,
            display_name="Morgan",
            user=User.objects.create_user("morgan"),
        )
        cls.outsider = m.Parent.objects.create(
            family=cls.stranger,
            display_name="Sam",
            user=User.objects.create_user("sam"),
        )
        cls.child = m.Child.objects.create(family=cls.family, name="Alex")
        cls.sibling = m.Child.objects.create(family=cls.family, name="Noah")
        cls.peer = m.Child.objects.create(family=cls.other, name="Emma")
        cls.excluded = m.Child.objects.create(family=cls.other, name="Robin")
        cls.group = m.ConferenceGroup.objects.create(
            name="Friends", approved_by=cls.parent
        )
        cls.group.members.add(cls.child)

    def setUp(self):
        self.client.force_login(self.parent.user)

    def url(self, name, *args):
        return reverse("directory:" + name, args=args)

    def invite(self):
        response = self.client.post(
            self.url("group_invite", self.group.pk), {"family": self.other.pk}
        )
        self.assertRedirects(response, self.url("invitations") + "?tab=sent")
        return m.GroupInvitation.objects.get(group=self.group)

    def test_single_child_can_start_group_then_invite_without_granting_calls(self):
        response = self.client.post(
            self.url("conference_group_create"),
            {
                "name": "New friends",
                "members": [self.child.pk],
                "is_active": "on",
            },
        )
        self.assertRedirects(response, self.url("connections"))
        new_group = m.ConferenceGroup.objects.get(name="New friends")
        self.assertFalse(new_group.calling_enabled)
        invitation = self.invite()
        self.assertEqual(invitation.sent_by, self.parent)
        self.assertEqual(list(self.group.members.all()), [self.child])
        self.assertFalse(m.ChildConnection.objects.exists())
        self.assertContains(
            self.client.get(self.url("invitations") + "?tab=sent"), "Friends"
        )
        self.client.force_login(self.recipient.user)
        self.assertContains(
            self.client.get(self.url("invitations")), "Review group invitation"
        )

    def test_accept_selects_only_own_children_preserves_members_and_records_approval(
        self,
    ):
        invitation = self.invite()
        self.client.force_login(self.recipient.user)
        review = self.client.get(self.url("group_review", invitation.pk))
        self.assertContains(review, "Current families: River")
        self.assertNotContains(review, "Alex")
        response = self.client.post(
            self.url("group_review", invitation.pk), {"members": [self.peer.pk]}
        )
        self.assertRedirects(response, self.url("connections"))
        self.assertEqual(set(self.group.members.all()), {self.child, self.peer})
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "accepted")
        self.assertEqual(invitation.responded_by, self.recipient)
        self.assertEqual(list(invitation.accepted_children.all()), [self.peer])
        self.assertFalse(m.ChildConnection.objects.exists())
        self.assertTrue(
            LogEntry.objects.filter(
                user=self.recipient.user, object_id=str(self.group.pk)
            ).exists()
        )
        self.assertTrue(
            m.FamilyActivity.objects.filter(
                family=self.family, description__contains="membership"
            ).exists()
        )
        self.assertTrue(
            m.FamilyActivity.objects.filter(
                family=self.other, description="Joined Friends with 1 child."
            ).exists()
        )
        # An already consumed invitation cannot add a later child or restore a departure.
        self.group.members.remove(self.peer)
        self.client.post(
            self.url("group_review", invitation.pk), {"members": [self.excluded.pk]}
        )
        self.assertEqual(list(self.group.members.all()), [self.child])

    def test_acceptance_with_maximum_length_names_keeps_activity_bounded(self):
        self.group.name = "G" * 200
        self.group.save()
        for child, initial in ((self.peer, "E"), (self.excluded, "R")):
            child.name = initial * 200
            child.save()
        invitation = self.invite()
        self.client.force_login(self.recipient.user)

        response = self.client.post(
            self.url("group_review", invitation.pk),
            {"members": [self.peer.pk, self.excluded.pk]},
        )

        self.assertRedirects(response, self.url("connections"))
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "accepted")
        self.assertEqual(
            set(self.group.members.all()), {self.child, self.peer, self.excluded}
        )
        activity = m.FamilyActivity.objects.filter(family=self.other).latest("pk")
        self.assertEqual(
            activity.description, f"Joined {self.group.name} with 2 children."
        )
        self.assertLessEqual(len(activity.description), 500)
        audit = LogEntry.objects.get(
            user=self.recipient.user, object_id=str(self.group.pk)
        )
        self.assertIn(self.peer.name, audit.change_message)
        self.assertIn(self.excluded.name, audit.change_message)

    def test_shared_group_edit_preserves_other_family_and_shared_settings(self):
        self.group.members.add(self.peer)
        url = self.url("conference_group_update", self.group.pk)
        response = self.client.get(url)
        self.assertEqual(set(response.context["form"].fields), {"members"})
        self.assertNotContains(response, "Emma")
        self.assertRedirects(
            self.client.post(
                url,
                {
                    "members": [self.sibling.pk],
                    "name": "Hijacked",
                    "notes": "Changed",
                    "calling_enabled": "on",
                    "dial_extension": "9999",
                    "approved_by": self.recipient.pk,
                },
            ),
            self.url("connections"),
        )
        self.group.refresh_from_db()
        self.assertEqual(set(self.group.members.all()), {self.sibling, self.peer})
        self.assertEqual(self.group.name, "Friends")
        self.assertEqual(self.group.notes, "")
        self.assertTrue(self.group.is_active)
        self.assertFalse(self.group.calling_enabled)
        self.assertIsNone(self.group.dial_extension)
        self.assertEqual(self.group.approved_by, self.parent)

    def test_leave_removes_call_routes_and_shortcuts_and_prevents_reentry(self):
        self.group.members.add(self.peer)
        self.group.calling_enabled = True
        self.group.save()
        phone = m.Device.objects.create(
            assigned_child=self.child,
            friendly_name="Bedroom",
            sip_extension="4101",
            sip_username="test-alex",
            sip_secret="fictional-test-only",
        )
        m.Device.objects.create(
            assigned_child=self.peer,
            friendly_name="Desk",
            sip_extension="4102",
            sip_username="test-emma",
            sip_secret="fictional-test-only",
        )
        shortcut = m.DialShortcut.objects.create(
            source_device=phone,
            digits="2",
            conference_group_target=self.group,
            approved_by=self.parent,
        )
        self.assertTrue(shortcut_destination_allowed(shortcut))
        self.assertEqual(len(build_asterisk_configuration().conference_routes), 1)
        url = self.url("conference_group_update", self.group.pk)
        self.assertRedirects(self.client.post(url, {}), self.url("connections"))
        self.assertEqual(list(self.group.members.all()), [self.peer])
        shortcut.refresh_from_db()
        self.assertFalse(shortcut_destination_allowed(shortcut))
        config = build_asterisk_configuration()
        self.assertEqual(config.conference_routes, ())
        self.assertEqual(config.shortcut_rules, ())
        self.assertEqual(
            self.client.post(url, {"members": [self.child.pk]}).status_code, 404
        )
        self.assertEqual(
            self.client.get(self.url("group_invite", self.group.pk)).status_code, 404
        )

    def test_last_family_can_leave_empty_group(self):
        self.client.post(
            self.url("conference_group_update", self.group.pk),
            {
                "name": "Friends",
                "is_active": "on",
                "members": [],
            },
        )
        self.assertFalse(self.group.members.exists())

    def test_rejects_foreign_members_in_create_update_and_accept(self):
        self.assertEqual(
            self.client.post(
                self.url("conference_group_create"),
                {
                    "name": "Invalid",
                    "members": [self.child.pk, self.peer.pk],
                    "is_active": "on",
                },
            ).status_code,
            200,
        )
        self.assertFalse(m.ConferenceGroup.objects.filter(name="Invalid").exists())
        response = self.client.post(
            self.url("conference_group_update", self.group.pk),
            {
                "name": "Friends",
                "members": [self.peer.pk],
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        invitation = self.invite()
        self.client.force_login(self.recipient.user)
        for selection in ([self.child.pk], []):
            response = self.client.post(
                self.url("group_review", invitation.pk), {"members": selection}
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(list(self.group.members.all()), [self.child])
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "pending")

    def test_unrelated_households_cannot_read_or_mutate_group_or_invitation(self):
        invitation = self.invite()
        self.client.force_login(self.outsider.user)
        for name, args in [
            ("conference_group_update", [self.group.pk]),
            ("group_invite", [self.group.pk]),
            ("group_review", [invitation.pk]),
            ("group_invitation_action", [invitation.pk, "cancel"]),
            ("group_invitation_action", [invitation.pk, "decline"]),
        ]:
            with self.subTest(name=name, args=args):
                self.assertEqual(
                    self.client.post(self.url(name, *args), {}).status_code, 404
                )
        self.assertNotContains(self.client.get(self.url("connections")), "Friends")
        self.assertNotContains(self.client.get(self.url("invitations")), "Friends")

    def test_private_family_requires_current_code_and_duplicates_are_rejected(self):
        url = self.url("group_invite", self.group.pk)
        self.assertNotContains(self.client.get(url), "Cedar")
        self.assertEqual(
            self.client.post(url, {"family": self.stranger.pk}).status_code, 200
        )
        self.assertFalse(m.GroupInvitation.objects.exists())
        self.assertRedirects(
            self.client.post(url, {"code": self.stranger.invite_code}),
            self.url("invitations") + "?tab=sent",
        )
        self.assertEqual(
            self.client.post(url, {"code": self.stranger.invite_code}).status_code, 200
        )
        self.assertEqual(m.GroupInvitation.objects.count(), 1)
        self.assertEqual(
            self.client.post(url, {"code": self.family.invite_code}).status_code, 200
        )

    def test_decline_cancel_and_get_requests_do_not_grant_membership(self):
        invitation = self.invite()
        url = self.url("group_invitation_action", invitation.pk, "cancel")
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.recipient.user)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.post(self.url("group_invitation_action", invitation.pk, "decline"))
        self.client.post(
            self.url("group_review", invitation.pk), {"members": [self.peer.pk]}
        )
        self.assertEqual(list(self.group.members.all()), [self.child])
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "declined")
        self.client.force_login(self.parent.user)
        self.client.post(
            self.url("group_invite", self.group.pk), {"family": self.other.pk}
        )
        pending = m.GroupInvitation.objects.get(status="pending")
        self.client.post(self.url("group_invitation_action", pending.pk, "cancel"))
        self.client.force_login(self.recipient.user)
        self.client.post(
            self.url("group_review", pending.pk), {"members": [self.peer.pk]}
        )
        self.assertEqual(list(self.group.members.all()), [self.child])

    def test_departure_cancels_pending_invitations(self):
        invitation = self.invite()
        self.client.post(
            self.url("conference_group_update", self.group.pk),
            {"name": "Friends", "is_active": "on"},
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "cancelled")
        self.client.force_login(self.recipient.user)
        self.client.post(
            self.url("group_review", invitation.pk), {"members": [self.peer.pk]}
        )
        self.assertFalse(self.group.members.exists())

    def test_revoked_sender_and_paused_group_cannot_authorize_join(self):
        invitation = self.invite()
        self.client.force_login(self.recipient.user)
        for kind in ("guardian", "account", "group", "membership"):
            with self.subTest(kind=kind):
                m.Parent.objects.filter(pk=self.parent.pk).update(
                    is_guardian=kind != "guardian"
                )
                User.objects.filter(pk=self.parent.user_id).update(
                    is_active=kind != "account"
                )
                m.ConferenceGroup.objects.filter(pk=self.group.pk).update(
                    is_active=kind != "group"
                )
                if kind == "membership":
                    self.group.members.clear()
                response = self.client.post(
                    self.url("group_review", invitation.pk), {"members": [self.peer.pk]}
                )
                self.assertRedirects(response, self.url("invitations"))
                self.assertFalse(self.group.members.filter(pk=self.peer.pk).exists())
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "pending")

    def test_guardian_login_and_csrf_required(self):
        url = self.url("group_invite", self.group.pk)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.parent.user)
        m.Parent.objects.filter(pk=self.parent.pk).update(is_guardian=False)
        self.assertEqual(
            self.client.post(url, {"family": self.other.pk}).status_code, 403
        )
        m.Parent.objects.filter(pk=self.parent.pk).update(is_guardian=True)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.parent.user)
        self.assertEqual(client.post(url, {"family": self.other.pk}).status_code, 403)
        self.assertFalse(m.GroupInvitation.objects.exists())


class ConcurrentGroupMembershipTests(TransactionTestCase):
    def setUp(self):
        self.parents = []
        self.children = []
        for index in range(2):
            family = m.Family.objects.create(name=f"Fictional family {index}")
            self.parents.append(
                m.Parent.objects.create(
                    family=family,
                    display_name=f"Guardian {index}",
                    user=User.objects.create_user(f"guardian-{index}"),
                )
            )
            self.children.append(
                [
                    m.Child.objects.create(family=family, name=f"Child {index}-{n}")
                    for n in range(2)
                ]
            )
        self.group = m.ConferenceGroup.objects.create(name="Friends")
        self.group.members.add(*(children[0] for children in self.children))

    def concurrent_posts(self, requests):
        barrier = Barrier(2)

        def post(item):
            parent, url, data = item
            close_old_connections()
            try:
                client = Client()
                client.force_login(parent.user)
                barrier.wait(timeout=10)
                return client.post(url, data).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(post, requests))

    def test_two_families_membership_edits_do_not_overwrite_each_other(self):
        url = reverse("directory:conference_group_update", args=[self.group.pk])
        responses = self.concurrent_posts(
            [
                (parent, url, {"members": [children[1].pk]})
                for parent, children in zip(self.parents, self.children)
            ]
        )
        self.assertEqual(responses, [302, 302])
        self.assertEqual(set(self.group.members.all()), {c[1] for c in self.children})

    def test_simultaneous_acceptance_consumes_invitation_once(self):
        self.group.members.remove(self.children[1][0])
        invitation = m.GroupInvitation.objects.create(
            group=self.group,
            source_family=self.parents[0].family,
            target_family=self.parents[1].family,
            sent_by=self.parents[0],
        )
        url = reverse("directory:group_review", args=[invitation.pk])
        responses = self.concurrent_posts(
            [
                (self.parents[1], url, {"members": [child.pk]})
                for child in self.children[1]
            ]
        )
        self.assertEqual(responses, [302, 302])
        self.assertEqual(self.group.members.count(), 2)
        self.assertEqual(invitation.accepted_children.count(), 1)
        self.assertEqual(
            LogEntry.objects.filter(object_id=str(self.group.pk)).count(), 1
        )
