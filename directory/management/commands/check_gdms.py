"""Read-only account/inventory check for the WP816 compatibility gate."""

import re

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from directory.gdms import GDMSClient, GDMSError, GDMSSettings, normalize_mac


class Command(BaseCommand):
    help = "Check GDMS API access without enrolling, configuring, or upgrading devices."

    def add_arguments(self, parser):
        parser.add_argument("--org-id", type=int, help="Explicit GDMS organization ID.")
        parser.add_argument("--site-id", type=int, help="Verify this site belongs to the organization.")
        parser.add_argument("--mac", help="Optionally check an already-enrolled phone.")

    def handle(self, *args, **options):
        org_id, site_id, mac = options["org_id"], options["site_id"], options["mac"]
        if (site_id or mac) and not org_id:
            raise CommandError("--site-id and --mac require --org-id.")
        try:
            if mac:
                mac = normalize_mac(mac)
            client = GDMSClient(GDMSSettings.from_django())
            organizations = client.organizations()
            ids = [row.get("id") for row in organizations]
            if any(type(value) is not int or value <= 0 for value in ids):
                raise GDMSError("GDMS returned invalid organization identifiers.")
            self.stdout.write("API authentication succeeded. Organization IDs: " + ", ".join(map(str, ids)))
            if org_id is None:
                self.stdout.write("Repeat with --org-id to verify sites. No devices were changed.")
                return
            if org_id not in ids:
                raise CommandError("The selected organization is not accessible to this account.")
            sites = client.sites(org_id)
            site_ids = []

            def collect(rows, depth=0):
                if depth > 20:
                    raise GDMSError("GDMS site hierarchy exceeded the depth limit.")
                for row in rows:
                    if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] <= 0:
                        raise GDMSError("GDMS returned invalid site identifiers.")
                    site_ids.append(row["id"])
                    children = row.get("children", [])
                    if not isinstance(children, list):
                        raise GDMSError("GDMS returned an invalid site hierarchy.")
                    collect(children, depth + 1)

            collect(sites)
            self.stdout.write("Site IDs: " + ", ".join(map(str, site_ids)))
            if site_id is not None and site_id not in site_ids:
                raise CommandError("The selected site does not belong to this organization.")
            if mac:
                device = client.device(mac, org_id)
                if device is None:
                    self.stdout.write("The requested device is not enrolled in this organization.")
                else:
                    # Do not print raw responses, MAC/SN, addresses, or provider text.
                    model, firmware = device.get("deviceType"), device.get("firmwareVersion")
                    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", model):
                        raise GDMSError("GDMS returned an invalid model identifier.")
                    if firmware is not None and (
                        not isinstance(firmware, str) or not re.fullmatch(r"\d+(?:\.\d+){1,7}", firmware)
                    ):
                        raise GDMSError("GDMS returned an unrecognized firmware version.")
                    status = device.get("status")
                    if type(status) is not int:
                        raise GDMSError("GDMS returned an invalid device status.")
                    self.stdout.write(f"Model: {model}; reported firmware: {firmware or 'not yet reported'}; status code: {status}.")
                    self.stdout.write("Inventory status alone does not prove current phone connectivity or successful provisioning.")
            self.stdout.write("Read-only check complete. No devices were changed.")
        except (GDMSError, ImproperlyConfigured, ValueError) as error:
            raise CommandError(str(error)) from None
