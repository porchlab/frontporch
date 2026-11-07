import time

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.views.decorators.debug import sensitive_variables

from directory.wireguard import reconcile_once
from frontporch.vpn_config import VPNConfigurationError


class Command(BaseCommand):
    help = "Publish active family peers to the private WireGuard container."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    @sensitive_variables()
    def handle(self, *args, **options):
        try:
            while True:
                close_old_connections()
                count = reconcile_once()
                if options["once"]:
                    self.stdout.write(f"Published {count} active peers. Runtime acknowledgement remains separate.")
                    return
                time.sleep(10)
        except (ImproperlyConfigured, ValidationError, VPNConfigurationError, OSError):
            raise CommandError("Peer reconciliation stopped. Check private operator configuration; the last snapshot expires within five minutes.") from None
