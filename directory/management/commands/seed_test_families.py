from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
import secrets

from directory.models import Child, Device, Family, Parent


TEST_FAMILIES = (
    {
        "name": "Maple",
        "family_phone": "2642",
        "parents": (
            ("8468", "Morgan"),
            ("7749", "Drew"),
        ),
        "children": (
            ("4754", "Casey"),
            ("5249", "Jordan"),
        ),
    },
    {
        "name": "River",
        "family_phone": "7747",
        "parents": (
            ("6255", "Taylor"),
            ("7981", "Riley"),
        ),
        "children": (("3552", "Alex"),),
    },
    {
        "name": "Cedar",
        "family_phone": "1440",
        "parents": (
            ("5963", "Sam"),
            ("2362", "Quinn"),
        ),
        "children": (
            ("7307", "Jamie"),
            ("2148", "Robin"),
            ("3152", "Sky"),
        ),
    },
)


class Command(BaseCommand):
    help = "Seed reusable local FrontPorch test families and devices."

    @transaction.atomic
    def handle(self, *args, **options):
        family_count = 0
        parent_count = 0
        child_count = 0
        device_count = 0

        for family_data in TEST_FAMILIES:
            family, _ = Family.objects.update_or_create(
                name=family_data["name"],
                defaults={"notes": "Reusable local test family."},
            )
            family_count += 1

            self._upsert_device(
                extension=family_data["family_phone"],
                friendly_name=f"{family.name} family phone",
                assigned_family=family,
            )
            device_count += 1

            for extension, display_name in family_data["parents"]:
                parent = Parent.objects.filter(
                    family=family, display_name=display_name
                ).first()
                if parent is None:
                    user = User.objects.create_user(
                        username=f"guardian_{secrets.token_hex(12)}",
                        password=secrets.token_urlsafe(48),
                    )
                    parent = Parent.objects.create(
                        family=family,
                        display_name=display_name,
                        user=user,
                        dial_extension=extension,
                    )
                elif not parent.is_guardian:
                    parent.is_guardian = True
                    parent.save(update_fields=["is_guardian", "updated_at"])
                parent_count += 1
                self._upsert_device(
                    extension=parent.dial_extension,
                    friendly_name=f"{display_name} phone",
                    assigned_parent=parent,
                )
                device_count += 1

            for extension, name in family_data["children"]:
                child, _ = Child.objects.update_or_create(
                    family=family,
                    name=name,
                    defaults={},
                )
                child_count += 1
                self._upsert_device(
                    extension=extension,
                    friendly_name=f"{name} phone",
                    assigned_child=child,
                )
                device_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded "
                f"{family_count} families, "
                f"{parent_count} parents, "
                f"{child_count} children, and "
                f"{device_count} devices."
            )
        )

    def _upsert_device(
        self,
        *,
        extension,
        friendly_name,
        assigned_child=None,
        assigned_parent=None,
        assigned_family=None,
    ):
        Device.objects.update_or_create(
            sip_username=extension,
            defaults={
                "assigned_child": assigned_child,
                "assigned_parent": assigned_parent,
                "assigned_family": assigned_family,
                "friendly_name": friendly_name,
                "sip_extension": extension,
                "sip_secret": f"test-{extension}",
                "is_active": True,
            },
        )
