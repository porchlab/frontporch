"""Explicit operator-only pilot; never starts as part of application startup."""

import json
import os
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.views.decorators.debug import sensitive_variables

from directory.provisioning_pilot import PilotProfile, pilot_server
from directory.wp816 import WP816ConfigurationError, device_profile


class Command(BaseCommand):
    help = "Serve one expiring WP816 profile on loopback for the HTTPS compatibility test."

    def add_arguments(self, parser):
        parser.add_argument("--mac", required=True)
        parser.add_argument("--wireguard-config", required=True)
        parser.add_argument("--sip-config", required=True)
        parser.add_argument("--state-file", required=True)
        parser.add_argument("--verified-firmware", required=True, choices=["1.0.3.39"])
        parser.add_argument("--port", type=int, default=18765)
        parser.add_argument("--lifetime", type=int, default=1800)

    @sensitive_variables()
    def handle(self, *args, **options):
        if not 1024 <= options["port"] <= 65535:
            raise CommandError("Use an unprivileged loopback port.")
        try:
            wg = Path(options["wireguard_config"]).read_text()
            sip = json.loads(Path(options["sip_config"]).read_text())
            xml = device_profile(options["mac"], wg, sip)
            profile = PilotProfile(options["mac"], xml, lifetime=options["lifetime"])
        except WP816ConfigurationError as error:
            raise CommandError(str(error)) from None
        except (OSError, ValueError):
            raise CommandError("Cannot load the local pilot configuration or lifetime.") from None
        server = pilot_server(profile, options["port"], lambda code: self.stdout.write(f"Profile request: HTTP {code}"))
        try:
            state = Path(options["state_file"])
            state.parent.mkdir(parents=True, exist_ok=True)
            # Never replace an existing pilot or disclose authentication in stdout.
            fd = os.open(state, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump({"username": profile.username, "password": profile.password,
                           "path": profile.path, "prefix": profile.prefix,
                           "expires_at": profile.expires_at, "port": options["port"]}, stream)
            self.stdout.write("Pilot ready on loopback. Credentials written only to the private state file.")
            while time.time() < profile.expires_at:
                server.handle_request()
        except FileExistsError:
            raise CommandError("Pilot state already exists; reconcile the previous pilot first.") from None
        finally:
            server.server_close()
