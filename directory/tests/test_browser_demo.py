"""Keep the browser's public exports and simulated permissions aligned with Django."""

from directory.tests.factories import create_user

import json
from datetime import date
from pathlib import Path
import shutil
import subprocess
from unittest import skipUnless

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.template.loader import render_to_string

from directory.management.commands.export_browser_demo import exported_assets
from directory.models import (
    Child,
    ChildConnection,
    Device,
    DialShortcut,
    ExternalPhoneNumber,
    Family,
    FamilyContact,
    Parent,
)
from directory.services import shortcut_destinations
from directory.phonebook import PhonebookEntry, device_phonebook


class BrowserDemoAssetsTests(SimpleTestCase):
    def test_committed_exports_match_real_django_presentation(self):
        root = Path(settings.BASE_DIR) / "ui-prototype/dist"
        for name, content in exported_assets().items():
            with self.subTest(asset=name):
                self.assertEqual(
                    (root / name).read_bytes(),
                    content,
                    "Run python manage.py export_browser_demo to refresh browser assets.",
                )
        self.assertEqual(
            (Path(settings.BASE_DIR) / "directory/static/directory/phonebook-fonts.js").read_bytes(),
            exported_assets()["phonebook-fonts.js"],
        )


@skipUnless(shutil.which("node"), "Node is required for the HTML-to-PDF check.")
class PhonebookDOMTests(SimpleTestCase):
    def test_django_card_variants_pass_through_the_real_dom_extractor(self):
        entries = [
            PhonebookEntry(
                "Alex",
                "River family",
                "7000",
                [
                    {"digits": "1", "label": "Alex"},
                    {"digits": "2", "label": "Best & <buddy>"},
                ],
            ),
            PhonebookEntry(
                "Élodie",
                "Maple family",
                "5200",
                [
                    {"digits": "4", "label": "Call home"},
                ],
            ),
            PhonebookEntry("Grandma <June>", "Family contact", "6100"),
        ]
        base = {
            "child": {"id": 1, "name": 'Casey & "C"'},
            "phone_name": "Bedroom <north>", "phone_extension": "4754",
            "phone_active": True, "printed_on": date(2026, 9, 20),
            "entries": entries,
        }
        pick_up = "Pick up the phone. Dial an extension or use a shortcut."
        at_menu = "At the menu, dial an extension or a shortcut below."
        empty_notice = (
            "No calls available yet. Ask a parent or guardian to check your "
            "connections and contacts, then print a new card."
        )
        access_numbers = [f"+12025550{n}" for n in range(100, 200)]
        # These are real Django template renders, not copied HTML fixtures.
        variants = [
            ("phone", {}, [pick_up], ""),
            ("empty", {"entries": []}, [pick_up], empty_notice),
            ("inactive", {"entries": [], "phone_active": False}, [
                "This phone is not enabled yet. Print a new card after your installer activates it."
            ], ""),
            ("landline", {"is_landline": True, "dial_in_numbers": access_numbers[:2]}, [
                f"First, call FrontPorch: {' or '.join(access_numbers[:2])}", at_menu,
            ], ""),
            ("direct landline", {"is_landline": True, "direct_call": True,
                "dial_in_numbers": access_numbers[:1], "entries": [PhonebookEntry("Alex", "River family", "7000")]}, [
                f"First, call FrontPorch: {access_numbers[0]}",
                "Your call connects directly to Alex. No extension or shortcut is needed.",
            ], ""),
            ("pending landline", {"is_landline": True, "dial_in_numbers": [], "entries": []}, [
                "FrontPorch dial-in is not set up yet. Ask your installer to set it up, then print a new card."
            ], empty_notice),
            ("long landline", {"child": {"id": 1, "name": "W" * 200},
                "phone_name": "Landline", "is_landline": True, "dial_in_numbers": access_numbers}, [
                f"First, call FrontPorch: {' or '.join(access_numbers)}", at_menu,
            ], ""),
        ]
        cases = []
        expected = []
        for name, changes, guide, empty in variants:
            context = {**base, **changes}
            for paper in ("letter", "a4"):
                for color in (False, True):
                    cases.append({
                        "html": render_to_string("directory/phonebook.html", {**context, "color": color}),
                        "options": {"paper": paper, "color": color},
                    })
                    expected.append((name, paper, color, {
                        "title": f"{context['child']['name']}’s phonebook.",
                        "identity": f"{context['phone_name']} · My extension 4754",
                        "guide": guide, "empty": empty,
                        "entries": [{
                            "name": entry.name, "description": entry.description,
                            "extension": entry.extension or "Use shortcut",
                            "shortcuts": [{
                                "digits": shortcut["digits"],
                                "label": shortcut["label"] if shortcut["label"] != entry.name else "",
                            } for shortcut in entry.shortcuts],
                        } for entry in context["entries"]],
                        "reminders": [
                            "A little reminder Quiet hours still apply. If a call doesn’t connect, ask a grown-up.",
                            "FrontPorch cannot call 911. Use another phone for emergencies.",
                        ],
                        "metadata": ["Made Sep 20, 2026 · Reprint when your circle changes.",
                            "Your family’s private phonebook."],
                    }))
        result = subprocess.run(
            [shutil.which("node"), "ui-prototype/tests/phonebook-dom-runner.cjs"],
            input=json.dumps(cases), cwd=settings.BASE_DIR, text=True,
            capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(result.stdout)
        self.assertEqual(len(actual), len(expected))
        for (name, paper, color, data), pdf in zip(expected, actual):
            with self.subTest(variant=name, paper=paper, color=color):
                self.assertEqual(pdf["data"], data)
                for entry in data["entries"]:
                    self.assertIn(entry["name"], pdf["text"])


@skipUnless(shutil.which("node"), "Node is required for the cross-runtime demo check.")
class BrowserDemoPermissionParityTests(TestCase):
    def test_selected_pairs_and_revoked_shortcuts_match_django(self):
        local = Family.objects.create(name="Demo Maple")
        remote = Family.objects.create(name="Demo Cedar")
        local_parent = Parent.objects.create(
            user=create_user(),
            family=local,
            display_name="Morgan",
            phone="2025550188",
            call_destination="both",
            dial_extension="5820",
        )
        remote_parent = Parent.objects.create(
            user=create_user(),
            family=remote,
            display_name="Sam",
        )
        children = [
            Child.objects.create(family=local, name=name)
            for name in ("Casey", "Jordan")
        ]
        peers = [
            Child.objects.create(family=remote, name=name) for name in ("Robin", "Wren")
        ]
        devices = []
        for n, child in enumerate(children + peers):
            devices.append(
                Device.objects.create(
                    assigned_child=child,
                    friendly_name=f"{child.name} phone",
                    sip_extension=str(5800 + n),
                    sip_username=f"demo-{n}",
                    sip_secret="fictional-test-secret",
                    is_active=True,
                )
            )
        parent_device = Device.objects.create(
            assigned_parent=local_parent,
            friendly_name="Morgan's desk",
            sip_extension="5820",
            sip_username="fictional-parent-desk",
            sip_secret="fictional-parent-secret",
        )
        # A second device owned by the same child is an allowed local destination.
        second = Device.objects.create(
            assigned_child=children[0],
            friendly_name="Desk phone",
            sip_extension="5810",
            sip_username="demo-desk",
            sip_secret="fictional-test-secret",
            is_active=True,
        )
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized("202-555-0199")
        contact = FamilyContact.objects.create(
            family=local, label="Grandma", external_phone_number=number
        )

        # The fixture uses stable IDs supplied by the database, never production data.
        def demo_child(child, phones):
            return {
                "id": str(child.pk),
                "name": child.name,
                "quietHours": [],
                "devices": [
                    {
                        "id": str(phone.pk),
                        "name": phone.friendly_name,
                        "extension": phone.sip_extension,
                        "active": phone.is_active,
                        "shortcuts": [],
                    }
                    for phone in phones
                ],
            }

        data = {
            "family": local.name,
            "children": [
                demo_child(children[0], [devices[0], second]),
                demo_child(children[1], [devices[1]]),
            ],
            "network": [
                {
                    "id": str(remote.pk),
                    "name": remote.name,
                    "children": [
                        demo_child(peers[0], [devices[2]]),
                        demo_child(peers[1], [devices[3]]),
                    ],
                }
            ],
            "guardians": [
                {
                    "id": str(local_parent.pk),
                    "name": local_parent.display_name,
                    "phone": local_parent.phone,
                    "extension": local_parent.dial_extension,
                    "callDestination": "both",
                    "devices": [{"active": True}],
                }
            ],
            "groups": [],
            "connections": [],
            "contacts": [
                {
                    "phone": number.normalized_number,
                    "name": "Grandma · External contact",
                    "extension": contact.dial_extension.dial_extension,
                }
            ],
            "invitations": [
                {
                    "id": "incoming",
                    "familyId": str(remote.pk),
                    "peerIds": [str(c.pk) for c in peers],
                    "childIds": [],
                    "direction": "incoming",
                    "status": "pending",
                }
            ],
        }
        expected = []
        for peer in peers:
            ChildConnection.objects.create(
                child_a=children[0],
                child_b=peer,
                approved_by_a=local_parent,
                approved_by_b=remote_parent,
            )

        DialShortcut.objects.create(
            source_device=devices[0],
            digits="1",
            internal_target_device=devices[2],
            approved_by=local_parent,
        )
        data["children"][0]["devices"][0]["shortcuts"].append(
            {
                "digits": "1",
                "active": True,
                "target": f"device:{devices[2].pk}",
            }
        )

        DialShortcut.objects.create(
            source_device=devices[0],
            digits="2",
            parent_target=local_parent,
            approved_by=local_parent,
        )
        data["children"][0]["devices"][0]["shortcuts"].append(
            {
                "digits": "2",
                "active": True,
                "target": f"parent:{local_parent.pk}",
            }
        )

        def snapshot():
            return {
                "pairs": sorted(
                    f"{pair.child_a_id}:{pair.child_b_id}"
                    for pair in ChildConnection.objects.filter(is_active=True)
                ),
                "targets": sorted(
                    (
                        target.friendly_name
                        if field == "internal_target_device"
                        else target.display_name if field == "parent_target" else label
                    )
                    for field, target, label in shortcut_destinations(
                        devices[0]
                    ).values()
                ),
                "phonebook": sorted(
                    (
                        {
                            "extension": entry.extension,
                            "shortcuts": [s["digits"] for s in entry.shortcuts],
                        }
                        for entry in device_phonebook(devices[0])
                    ),
                    key=lambda entry: entry["extension"],
                ),
            }

        expected.append(snapshot())
        ChildConnection.objects.filter(child_b=peers[0]).update(is_active=False)
        expected.append(snapshot())
        contact.delete()
        expected.append(snapshot())
        local_parent.call_destination = "disabled"
        local_parent.save()
        expected.append(snapshot())
        result = subprocess.run(
            [shutil.which("node"), "ui-prototype/tests/parity-runner.cjs"],
            input=json.dumps(
                {
                    "data": data,
                    "selected": [str(children[0].pk)],
                    "source": str(devices[0].pk),
                    "revokedPeer": str(peers[0].pk),
                }
            ),
            cwd=settings.BASE_DIR,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout), expected)
