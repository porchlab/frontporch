import time
import json
from pathlib import Path
from datetime import timedelta
from django.conf import settings

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, close_old_connections
from django.db.models import Q
from django.utils import timezone

from frontporch.vpn_runtime import atomic_private_file
from directory.enrollment_worker import EnrollmentWorker, validate_configuration, TERMINAL
from directory.models import PhoneEnrollment, PhoneEnrollmentState


class Command(BaseCommand):
    help = "Run the private WP816 provisioning worker; --once performs one bounded pass."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        validate_configuration()
        if settings.ASTERISK_AUTO_APPLY_CONFIG:
            raise CommandError("Worker requires ASTERISK_AUTO_APPLY_CONFIG=false; it applies durable changes explicitly.")
        worker = EnrollmentWorker()
        while True:
            close_old_connections()
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [0x4650454E524F4C])
                acquired = cursor.fetchone()[0]
            if acquired:
                try:
                    pending = PhoneEnrollment.objects.filter(next_attempt_at__lte=timezone.now()).filter(
                        ~Q(state__in=TERMINAL) | Q(state=PhoneEnrollmentState.READY, operations__kind="bootstrap")
                    ).exclude(state=PhoneEnrollmentState.READY, operations__kind="retire").distinct().order_by("next_attempt_at")[:10]
                    for enrollment in pending.select_related("assigned_child", "assigned_parent", "device__wireguard_peer", "requested_by", "family"):
                        try:
                            worker.step(enrollment)
                            if enrollment.consecutive_failures:
                                updates = {"consecutive_failures": 0}
                                if enrollment.problem == "service" and enrollment.state not in TERMINAL:
                                    updates["problem"] = ""
                                PhoneEnrollment.objects.filter(pk=enrollment.pk).update(**updates)
                        except Exception:
                            # No provider payloads, rendered XML, signed URLs, or DB values in logs.
                            failures = enrollment.consecutive_failures + 1
                            updates = {"next_attempt_at": timezone.now() + timedelta(seconds=60), "consecutive_failures": failures}
                            if failures >= 3 and enrollment.state not in TERMINAL:
                                updates["problem"] = "service"
                            PhoneEnrollment.objects.filter(pk=enrollment.pk).update(**updates)
                            self.stderr.write("Phone setup step deferred; private enrollment journal retains its outcome.")
                        atomic_private_file(Path(settings.PHONE_PROFILE_DIR) / "worker-health.json", json.dumps({"at": time.time()}))
                finally:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_unlock(%s)", [0x4650454E524F4C])
            atomic_private_file(Path(settings.PHONE_PROFILE_DIR) / "worker-health.json", json.dumps({"at": time.time()}))
            if options["once"]:
                break
            time.sleep(5)
