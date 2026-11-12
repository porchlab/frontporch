"""Read-only GDMS Networking adapter; deliberately separate from GDMS UC.

Contract: https://doc.grandstream.dev/GWN-API/EN/ (reviewed 2026-11-11).
Token requests use /oauth/token; signed data requests use /oapi/v1.0.0/.
No requests at import time, automatic retries, or device mutations.
"""

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.views.decorators.debug import sensitive_variables

from .gdms import _NoRedirects, normalize_mac, positive_id


class GWNError(Exception):
    """Sanitized error: never include provider messages, URLs, or responses."""


class GWNProtocolError(GWNError):
    pass


class GWNInventoryUnavailable(GWNProtocolError):
    """The provider returned no inventory envelope; identity remains unverified."""


@dataclass(frozen=True)
class GWNSettings:
    app_id: str = field(repr=False)
    secret_key: str = field(repr=False)
    region: str = "us"
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    timeout: float = 15

    def __post_init__(self):
        if self.region not in {"us", "eu"}:
            raise ValueError("GWN_REGION must be us or eu.")
        if not all(isinstance(v, str) and v.strip() for v in (self.app_id, self.secret_key)):
            raise ValueError("Configure GWN_APP_ID and GWN_SECRET_KEY for Networking.")
        if not all(isinstance(v, str) for v in (self.username, self.password)) or bool(self.username) != bool(self.password):
            raise ValueError("Set both GWN_USERNAME and GWN_PASSWORD for restricted-network access.")
        if (type(self.timeout) not in (int, float) or not math.isfinite(self.timeout)
                or not 0 < self.timeout <= 60):
            raise ValueError("Networking timeout must be between 0 and 60 seconds.")

    @property
    def base_url(self):
        return "https://www.gwn.cloud" if self.region == "us" else "https://eu.gwn.cloud"

    @classmethod
    def from_django(cls):
        # No UC credential fallback: these are separate operator configurations.
        names = ("app_id", "secret_key", "region", "username", "password")
        values = {name: getattr(settings, f"GWN_{name.upper()}", "us" if name == "region" else "") for name in names}
        if not values["app_id"] or not values["secret_key"]:
            raise ImproperlyConfigured("Configure GWN_APP_ID and GWN_SECRET_KEY in the private operator environment.")
        return cls(**values)


@dataclass(frozen=True)
class GWNDeviceObservation:
    mac: str = field(repr=False)
    network_id: int = field(repr=False)
    model: str
    firmware: str
    online: bool | None


def firmware_version(value):
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,3}){3}", value):
        raise GWNProtocolError("Networking returned an unrecognized firmware version.")
    return value


@sensitive_variables()
def signature(params, secret_key, body):
    """Bearer-header tokens are excluded, per the Networking signature contract."""
    fields = {**params, "secretKey": secret_key}
    canonical = "&".join(f"{key}={fields[key]}" for key in sorted(fields))
    return hashlib.sha256(f"&{canonical}&{hashlib.sha256(body).hexdigest()}&".encode()).hexdigest()


class GWNClient:
    MAX_RESPONSE_BYTES = 2 * 1024 * 1024
    MAX_PAGES = 100
    READ_PATHS = {"/network/list", "/ap/list", "/upgrade/version"}

    def __init__(self, config, *, opener=None, clock=time.time):
        self.config = config
        self.opener = opener or build_opener(_NoRedirects())
        self.clock = clock
        self._token = None
        self._token_expires = 0

    @sensitive_variables()
    def _send(self, path, body, *, query=None, token=None, form=False):
        url = self.config.base_url + path
        if query:
            url += "?" + urlencode(query)
        headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded" if form else "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            request = Request(url, data=body, headers=headers, method="POST")
            with self.opener.open(request, timeout=self.config.timeout) as response:
                raw = response.read(self.MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            if error.code in (401, 403):
                raise GWNError("Networking denied access. Check its API Developer credentials, region, and network restrictions.") from None
            raise GWNError("Networking HTTP request failed. No automatic retry was attempted.") from None
        except (URLError, OSError, TimeoutError, ValueError, HTTPException):
            raise GWNError("Networking request failed. No automatic retry was attempted.") from None
        if len(raw) > self.MAX_RESPONSE_BYTES:
            raise GWNProtocolError("Networking response exceeded the size limit.")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise GWNProtocolError("Networking returned invalid JSON.") from None
        if not isinstance(result, dict):
            raise GWNProtocolError("Networking returned an unexpected response shape.")
        return result

    @sensitive_variables()
    def authenticate(self):
        values = {"grant_type": "client_credentials", "client_id": self.config.app_id, "client_secret": self.config.secret_key}
        if self.config.username:
            password = hashlib.sha256(hashlib.md5(self.config.password.encode(), usedforsecurity=False).hexdigest().encode()).hexdigest()
            values.update(grant_type="password", username=self.config.username, password=password)
        # POST with form credentials was verified live. Never put secrets in URLs.
        result = self._send("/oauth/token", urlencode(values).encode(), form=True)
        token, expires = result.get("access_token"), result.get("expires_in")
        if (not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._~+/=-]{1,8192}", token)
                or type(expires) is not int or not 0 < expires <= 366 * 86400):
            raise GWNProtocolError("Networking did not return a valid token and lifetime.")
        self._token = token
        self._token_expires = self.clock() + max(0, expires - 30)

    @sensitive_variables()
    def _read(self, path, data):
        if path not in self.READ_PATHS:
            raise ValueError("Only the supported read-only Networking routes are allowed.")
        if not self._token or self.clock() >= self._token_expires:
            self.authenticate()
        body = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
        params = {"appID": self.config.app_id, "timestamp": str(int(self.clock() * 1000))}
        params["signature"] = signature(params, self.config.secret_key, body)
        result = self._send("/oapi/v1.0.0" + path, body, query=params, token=self._token)
        code = result.get("retCode")
        if type(code) is not int:
            raise GWNProtocolError("Networking response is missing a numeric status code.")
        if code != 0:
            raise GWNError(f"Networking rejected the read (code {code}).")
        if "data" not in result:
            raise GWNProtocolError("Networking response is missing data.")
        return result["data"]

    @staticmethod
    def _rows(data):
        if (not isinstance(data, dict) or not isinstance(data.get("result"), list)
                or any(not isinstance(row, dict) for row in data["result"])):
            raise GWNProtocolError("Networking returned an invalid list.")
        return data["result"]

    def _pages(self, path, payload, *, total_key, current_key):
        for page in range(1, self.MAX_PAGES + 1):
            data = self._read(path, {**payload, "pageNum": page, "pageSize": 100})
            if path == "/ap/list" and data == "":
                # Observed for an account without registered devices. It is not
                # the documented list envelope and cannot prove claim availability.
                raise GWNInventoryUnavailable("Networking returned no device inventory. Device identity remains unverified.")
            rows = self._rows(data)
            pages = data.get(total_key)
            current = data.get(current_key, page)
            if (type(pages) is not int or not 0 <= pages <= self.MAX_PAGES
                    or type(current) is not int or current != page
                    or len(rows) > 100 or (pages == 0 and rows)
                    or (pages < page and not (page == 1 and pages == 0))):
                raise GWNProtocolError("Networking returned invalid or excessive pagination.")
            yield from rows
            if page >= pages:
                return
        raise GWNProtocolError("Networking pagination exceeded the limit.")

    def network_ids(self):
        ids = []
        for row in self._pages("/network/list", {}, total_key="pages", current_key="pageNum"):
            network_id = row.get("id")
            if type(network_id) is not int or network_id <= 0 or network_id in ids:
                raise GWNProtocolError("Networking returned invalid or duplicate network identifiers.")
            ids.append(network_id)
        return ids

    def device(self, mac, network_id):
        mac, network_id = normalize_mac(mac), positive_id(network_id)
        found = None
        for row in self._pages("/ap/list", {"networkId": str(network_id), "search": mac,
                "filter": {"showType": "all"}}, total_key="totalPage", current_key="currentPage"):
            try:
                row_mac = normalize_mac(row.get("mac", ""))
            except (ValueError, AttributeError, TypeError):
                raise GWNProtocolError("Networking returned an invalid device identity.") from None
            if row_mac != mac:
                continue
            if found or type(row.get("networkId")) is not int or row["networkId"] != network_id:
                raise GWNProtocolError("Networking returned an ambiguous or wrong-network device.")
            if row.get("apType") != "GWN7062ET":
                raise GWNProtocolError("The selected device is not a GWN7062ET.")
            status = row.get("status")
            if type(status) is not int:
                raise GWNProtocolError("Networking returned an invalid device status.")
            found = GWNDeviceObservation(mac, network_id, "GWN7062ET", firmware_version(row.get("versionFirmware")),
                bool(status) if status in (0, 1) else None)
        return found

    def recommended_firmware(self, device):
        """A provider recommendation is neither an approved target nor live firmware."""
        rows = self._rows(self._read("/upgrade/version", {"networkId": device.network_id}))
        found = []
        for row in rows:
            try:
                mac = normalize_mac(row.get("mac", ""))
            except (ValueError, AttributeError, TypeError):
                raise GWNProtocolError("Networking returned an invalid firmware identity.") from None
            if mac == device.mac:
                if row.get("type") != device.model or found:
                    raise GWNProtocolError("Networking returned an ambiguous or wrong-model firmware recommendation.")
                found.append(firmware_version(row.get("lastVersion")))
        return found[0] if found else ""
