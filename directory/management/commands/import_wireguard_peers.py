"""Explicit operator import. Preview by default; no QNAP/server mutations."""

from pathlib import Path
import json
import sys

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.views.decorators.debug import sensitive_variables

from directory.wireguard import import_peers, imported_client_keys, parse_legacy_config
from frontporch.vpn_config import VPNConfigurationError
from frontporch.vpn_runtime import read_json


class Command(BaseCommand):
    help = "Preview/import existing WireGuard peers with explicit family assignments."

    def add_arguments(self, parser):
        parser.add_argument("--config", help="Private output of wg showconf, never a public artifact.")
        parser.add_argument("--assignments", help="Private JSON family/peer mapping.")
        parser.add_argument("--client-config", action="append", default=[], help="Optional known client .conf; required for an imported GDMS peer.")
        parser.add_argument("--bundle-stdin", action="store_true", help="Read a private JSON import bundle from stdin; no secrets in argv or remote temporary files.")
        parser.add_argument("--apply", action="store_true", help="Write the reviewed mapping to Django.")

    @sensitive_variables()
    def handle(self, *args, **options):
        try:
            if options["bundle_stdin"]:
                if options["config"] or options["assignments"] or options["client_config"]:
                    raise ValueError
                text = sys.stdin.read(1024 * 1024 + 1)
                if len(text) > 1024 * 1024:
                    raise ValueError
                bundle = json.loads(text)
                if not isinstance(bundle, dict) or set(bundle) != {"config", "assignments", "client_configs"}:
                    raise ValueError
            else:
                if not options["config"] or not options["assignments"]:
                    raise ValueError
                with Path(options["config"]).open() as stream:
                    text = stream.read(1024 * 1024 + 1)
                clients = []
                for filename in options["client_config"]:
                    with Path(filename).open() as stream:
                        clients.append(stream.read(16385))
                bundle = {"config": text, "assignments": read_json(Path(options["assignments"])), "client_configs": clients}
            legacy = parse_legacy_config(bundle["config"])
            peers = import_peers(legacy, bundle["assignments"], apply=options["apply"],
                                 client_keys=imported_client_keys(legacy, bundle["client_configs"]))
        except (VPNConfigurationError, ValidationError, ImproperlyConfigured, OSError, ValueError, TypeError):
            raise CommandError("Import rejected. Check the private configuration, family mapping, and existing ownership; no partial import was saved.") from None
        self.stdout.write(f"{'Imported' if options['apply'] else 'Validated'} {len(peers)} peers. Server configuration was not changed.")
