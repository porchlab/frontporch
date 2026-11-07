"""Isolated WSGI profile delivery: no Django, database, GDMS, AMI, or peer keyring.

Only the private worker writes expiring profile leases. The public process can
read those leases and write download receipts; it cannot extend or issue one.
"""

import base64
import binascii
import hashlib
import hmac
import json
import math
import os
import re
import time
from pathlib import Path

from .vpn_runtime import atomic_private_file

MAX_LEASE_SECONDS = 3600
MAX_FILE_BYTES = 128 * 1024
PATH = re.compile(r"/phone-profiles/([0-9a-f]{32})/cfg([0-9a-f]{12})\.xml\Z")


def password_digest(username, password):
    # Passwords are random 256-bit tokens; a fast hash doesn't enable guessing.
    return hashlib.sha256((username + ":" + password).encode()).hexdigest()


class ProfileApplication:
    def __init__(self, profile_dir=None, receipt_dir=None, clock=time.time):
        self.profile_dir = Path(profile_dir or os.environ["PHONE_PROFILE_DIR"])
        self.receipt_dir = Path(receipt_dir or os.environ["PHONE_RECEIPT_DIR"])
        self.clock = clock

    def __call__(self, environ, start_response):
        status, payload, extra = "404 Not Found", b"", []
        match = PATH.fullmatch(environ.get("PATH_INFO", ""))
        if (match and environ.get("REQUEST_METHOD") == "GET"
                and environ.get("HTTP_X_FORWARDED_PROTO") == "https"
                and not environ.get("QUERY_STRING")):
            status, extra = "401 Unauthorized", [("WWW-Authenticate", 'Basic realm="FrontPorch phone"')]
            try:
                auth = environ.get("HTTP_AUTHORIZATION", "")
                if len(auth) > 512 or not auth.startswith("Basic "):
                    raise ValueError
                credentials = base64.b64decode(auth[6:], validate=True).decode("ascii")
                username, password = credentials.split(":", 1)
                with (self.profile_dir / (match[1] + ".json")).open("rb") as f:
                    raw = f.read(MAX_FILE_BYTES + 1)
                if len(raw) > MAX_FILE_BYTES:
                    raise ValueError
                lease = json.loads(raw)
                now = self.clock()
                created, expires = lease["created"], lease["expires"]
                if (type(created) not in (int, float) or type(expires) not in (int, float)
                        or not math.isfinite(created) or not math.isfinite(expires)
                        or not created <= now < expires <= created + MAX_LEASE_SECONDS
                        or lease["id"] != match[1] or lease["mac"] != match[2]
                        or not hmac.compare_digest(lease["auth"], password_digest(username, password))):
                    raise ValueError
                payload = base64.b64decode(lease["xml"], validate=True)
                if not payload or len(payload) > 64 * 1024:
                    raise ValueError
                # Receipt means a response was prepared, not proof of handset apply.
                atomic_private_file(self.receipt_dir / (match[1] + ".json"), json.dumps({"id": match[1], "at": now}))
                status, extra = "200 OK", [("Content-Type", "application/xml; charset=utf-8")]
            except (OSError, ValueError, TypeError, KeyError, UnicodeError, binascii.Error):
                payload = b""
        start_response(status, [
            ("Cache-Control", "no-store, private"), ("Pragma", "no-cache"),
            ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"),
            ("Content-Length", str(len(payload))), *extra,
        ])
        return [payload]


def application(environ, start_response):
    return ProfileApplication()(environ, start_response)
