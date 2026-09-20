"""Keep the browser's public exports and simulated permissions aligned with Django."""

from directory.tests.factories import create_user

import json
from pathlib import Path
import shutil
import subprocess
from unittest import skipUnless

from django.conf import settings
from django.test import SimpleTestCase, TestCase

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
from directory.phonebook import device_phonebook


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


@skipUnless(shutil.which("node"), "Node is required for the cross-runtime demo check.")
class BrowserDemoPermissionParityTests(TestCase):
    def test_selected_pairs_and_revoked_shortcuts_match_django(self):
        local = Family.objects.create(name="Demo Maple")
        remote = Family.objects.create(name="Demo Cedar")
        local_parent = Parent.objects.create(
            user=create_user(),
            family=local,
            display_name="Morgan",
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
            "guardians": [],
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

        def snapshot():
            return {
                "pairs": sorted(
                    f"{pair.child_a_id}:{pair.child_b_id}"
                    for pair in ChildConnection.objects.filter(is_active=True)
                ),
                "targets": sorted(
                    label if field != "internal_target_device" else target.friendly_name
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
