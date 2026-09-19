from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TransactionTestCase

from directory.models import Child, Device, Family


class PhoneReservationConcurrencyTests(TransactionTestCase):
    def test_two_owners_cannot_claim_the_same_extension_concurrently(self):
        family = Family.objects.create(name="Concurrent test family")
        children = [
            Child.objects.create(family=family, name=name)
            for name in ("Casey", "Riley")
        ]
        barrier = Barrier(2)

        def reserve(child_id):
            close_old_connections()
            try:
                device = Device(
                    assigned_child_id=child_id,
                    friendly_name="Phone",
                    sip_extension="5891",
                    sip_username=f"phone-{child_id}",
                    sip_secret="fictional-secret",
                    is_active=False,
                )
                barrier.wait(timeout=10)
                try:
                    device.save()
                    return "created"
                except ValidationError:
                    return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(reserve, [child.pk for child in children]))
        self.assertCountEqual(results, ["created", "rejected"])
        self.assertEqual(Device.objects.filter(sip_extension="5891").count(), 1)
