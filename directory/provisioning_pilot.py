"""Isolated, expiring single-phone server for the hardware compatibility gate.

Not a production service and never mounted in Django's URL configuration.
Bind only to loopback, behind a TLS-terminating Cloudflare test tunnel.
"""

import base64
import hmac
import secrets
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from .gdms import normalize_mac


class PilotProfile:
    def __init__(self, mac, xml, *, lifetime=1800, clock=time.time):
        if not 60 <= lifetime <= 3600:
            raise ValueError("Pilot lifetime must be 60 to 3600 seconds.")
        self.clock = clock
        self.expires_at = clock() + lifetime
        self.prefix = "/pilot/" + secrets.token_urlsafe(24)
        self.path = f"{self.prefix}/cfg{normalize_mac(mac).lower()}.xml"
        self.username = secrets.token_hex(12)
        self.password = secrets.token_urlsafe(32)
        self._authorization = b"Basic " + base64.b64encode(f"{self.username}:{self.password}".encode())
        self._xml = xml
        self._window = clock()
        self._requests = 0

    def respond(self, method, path, headers):
        """No request/response contents or credentials are logged."""
        common = {"Cache-Control": "no-store, private, max-age=0", "Pragma": "no-cache",
                  "X-Content-Type-Options": "nosniff", "Content-Type": "text/plain"}
        now = self.clock()
        if now - self._window >= 60:
            self._window, self._requests = now, 0
        self._requests += 1
        if self._requests > 120:
            return 429, {**common, "Retry-After": "60"}, b""
        if now >= self.expires_at:
            return 410, common, b""
        if method != "GET":
            return 405, {**common, "Allow": "GET"}, b""
        if headers.get("X-Forwarded-Proto") != "https":
            return 403, common, b""
        if path != self.path:
            return 404, common, b""
        supplied = headers.get("Authorization", "").encode("utf-8")
        if not hmac.compare_digest(supplied, self._authorization):
            return 401, {**common, "WWW-Authenticate": 'Basic realm="FrontPorch provisioning"'}, b""
        return 200, {**common, "Content-Type": "application/xml; charset=utf-8"}, self._xml


def pilot_server(profile, port, report):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FrontPorchPilot"
        sys_version = ""

        def setup(self):
            self.request.settimeout(5)
            super().setup()

        def log_message(self, *args):
            pass

        def handle_request(self):
            code, headers, body = profile.respond(self.command, self.path, self.headers)
            self.send_response(code)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            report(code)

        do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = handle_request

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    return server
