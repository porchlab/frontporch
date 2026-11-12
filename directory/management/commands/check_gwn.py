"""Operator-only Networking check; never claims or changes a gateway."""

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from directory.gdms import normalize_mac, positive_id
from directory.gwn import GWNClient, GWNError, GWNSettings


class Command(BaseCommand):
    help = "Check GDMS Networking access and optional GWN7062ET inventory without changing devices."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--network-id", type=int, help="Explicit Networking network ID.")
        parser.add_argument("--mac", help="Optionally inspect this already-registered gateway.")

    def handle(self, *args, **options):
        network_id, mac = options["network_id"], options["mac"]
        if mac is not None and network_id is None:
            raise CommandError("--mac requires --network-id.")
        try:
            if network_id is not None:
                network_id = positive_id(network_id)
            if mac is not None:
                mac = normalize_mac(mac)
            client = GWNClient(GWNSettings.from_django())
            ids = client.network_ids()
            self.stdout.write("Networking authentication succeeded. Accessible network IDs: " + (", ".join(map(str, ids)) or "none"))
            if network_id is not None and network_id not in ids:
                raise CommandError("The selected network is not accessible to this account.")
            if mac is not None:
                device = client.device(mac, network_id)
                if device is None:
                    self.stdout.write("The requested gateway was not found in this network. This does not establish claim availability.")
                else:
                    status = {True: "online", False: "offline", None: "unknown"}[device.online]
                    recommendation = client.recommended_firmware(device)
                    self.stdout.write(f"Model: {device.model}; reported firmware: {device.firmware or 'unreported'}; cloud status: {status}.")
                    self.stdout.write("Provider-recommended firmware: " + (recommendation or "unreported") + ". This is not a reviewed FrontPorch firmware target.")
            else:
                self.stdout.write("Use --network-id and --mac to inspect an already-registered gateway.")
            self.stdout.write("Read-only check complete. No devices were changed. Inventory does not establish VPN, SIP, or audio readiness.")
        except (GWNError, ImproperlyConfigured, ValueError) as error:
            raise CommandError(str(error)) from None
