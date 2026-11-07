"""Small GDMS UC API client. No network requests occur at import time.

Contract: https://doc.grandstream.dev/GDMS-API/EN/ (reviewed 2026-10-31).
Never log request URLs: GDMS puts access tokens and signatures in the query.
Mutations are deliberately not retried: a lost response may have committed.
"""

import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.views.decorators.debug import sensitive_variables


class GDMSError(Exception):
    """Sanitized error; deliberately excludes provider messages and URLs."""


class GDMSProtocolError(GDMSError):
    pass


class GDMSAPIError(GDMSError):
    def __init__(self, code):
        self.code = code
        super().__init__(f"GDMS rejected the request (code {code}).")


class GDMSTransportError(GDMSError):
    """For writes, the outcome is unknown; reconcile before resubmission."""


def normalize_mac(value):
    value = value.strip()
    if not re.fullmatch(r"(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}|(?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2})", value):
        raise ValueError("Enter a valid MAC address from the device label.")
    return value.replace(":", "").replace("-", "").upper()


def wire_mac(value):
    value = normalize_mac(value)
    return ":".join(value[i:i + 2] for i in range(0, 12, 2))


def positive_id(value):
    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
        raise ValueError("GDMS identifiers must be positive integers.")
    return int(value)


@dataclass(frozen=True)
class GDMSSettings:
    username: str = field(repr=False)
    password: str = field(repr=False)
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    region: str = "us"
    timeout: float = 15

    def __post_init__(self):
        if self.region not in {"us", "eu"}:
            raise ValueError("GDMS region must be us or eu.")
        if not all((self.username, self.password, self.client_id, self.client_secret)):
            raise ValueError("GDMS credentials are incomplete.")
        if not 0 < self.timeout <= 60:
            raise ValueError("GDMS timeout must be between 0 and 60 seconds.")

    @property
    def base_url(self):
        host = "www.gdms.cloud" if self.region == "us" else "eu.gdms.cloud"
        return f"https://{host}/oapi"

    @classmethod
    def from_django(cls):
        values = {
            name: getattr(settings, f"GDMS_{name.upper()}", "")
            for name in ("username", "password", "client_id", "client_secret")
        }
        missing = [f"GDMS_{name.upper()}" for name, value in values.items() if not value]
        if missing:
            raise ImproperlyConfigured("Configure " + ", ".join(missing) + " in the local environment.")
        return cls(**values, region=getattr(settings, "GDMS_REGION", "us"))


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Even a same-host redirect can replay credentials onto an unintended path.
        return None


@sensitive_variables()
def signature(params, client_id, client_secret, body=None):
    """Sign the exact UTF-8 bytes that will be sent, per GDMS's JSON contract."""
    values = {**params, "client_id": client_id, "client_secret": client_secret}
    joined = "&".join(f"{key}={values[key]}" for key in sorted(values))
    if body is not None:
        joined += "&" + hashlib.sha256(body).hexdigest()
    return hashlib.sha256(f"&{joined}&".encode()).hexdigest()


class GDMSClient:
    MAX_RESPONSE_BYTES = 2 * 1024 * 1024

    def __init__(self, config, *, opener=None, clock=time.time):
        self.config = config
        self.opener = opener or build_opener(_NoRedirects())
        self.clock = clock
        self._token = None
        self._token_expires = 0

    @sensitive_variables()
    def _send(self, method, path, *, query=None, body=None, content_type=None):
        url = self.config.base_url + path
        if query:
            url += "?" + urlencode(query)
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.config.timeout) as response:
                payload = response.read(self.MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, OSError, TimeoutError, ValueError):
            # No exception chaining: HTTPError/URLError may contain signed URLs.
            raise GDMSTransportError(
                "GDMS request failed. For a write, verify its outcome before retrying."
            ) from None
        if len(payload) > self.MAX_RESPONSE_BYTES:
            raise GDMSProtocolError("GDMS response exceeded the size limit.")
        try:
            result = json.loads(payload)
        except (ValueError, UnicodeError):
            raise GDMSProtocolError("GDMS returned invalid JSON.") from None
        if not isinstance(result, dict):
            raise GDMSProtocolError("GDMS returned an unexpected response shape.")
        return result

    @sensitive_variables()
    def authenticate(self):
        # Use POST, as in the official API Guide; never put the password in a URL.
        password = hashlib.sha256(
            hashlib.md5(self.config.password.encode(), usedforsecurity=False).hexdigest().encode()
        ).hexdigest()
        body = urlencode({
            "username": self.config.username,
            "password": password,
            "grant_type": "password",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }).encode()
        result = self._send("POST", "/oauth/token", body=body,
                            content_type="application/x-www-form-urlencoded")
        token, expires = result.get("access_token"), result.get("expires_in")
        if not isinstance(token, str) or not token or type(expires) is not int or expires <= 0:
            raise GDMSProtocolError("GDMS did not return a valid access token and lifetime.")
        self._token = token
        self._token_expires = self.clock() + max(0, expires - 30)

    @sensitive_variables()
    def _request(self, method, path, *, query=None, data=None, form=None, xml=None):
        if not self._token or self.clock() >= self._token_expires:
            self.authenticate()
        params = {**(query or {}), "access_token": self._token,
                  "timestamp": str(int(self.clock() * 1000))}
        if xml is not None:
            # The official packet capture uses multipart/form-data, despite the
            # field table calling this application/x-www-form-urlencoded.
            fields = {**form, "xml": hashlib.md5(xml, usedforsecurity=False).hexdigest()}
            params["signature"] = signature({**params, **fields}, self.config.client_id,
                                            self.config.client_secret)
            boundary = "FrontPorch" + secrets.token_hex(24)
            parts = []
            for key, value in form.items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="xml"; filename="config.xml"\r\nContent-Type: application/xml\r\n\r\n'.encode() + xml + b"\r\n")
            parts.append(f"--{boundary}--\r\n".encode())
            body = b"".join(parts)
            content_type = f"multipart/form-data; boundary={boundary}"
        else:
            body = None if data is None else json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
            params["signature"] = signature(params, self.config.client_id,
                                            self.config.client_secret, body)
            content_type = "application/json" if body is not None else None
        result = self._send(method, "/v1.0.0" + path, query=params, body=body,
                            content_type=content_type)
        code = result.get("retCode")
        if type(code) is not int:
            raise GDMSProtocolError("GDMS response is missing a numeric status code.")
        if code != 0:
            raise GDMSAPIError(code)
        if "data" not in result:
            raise GDMSProtocolError("GDMS response is missing data.")
        return result["data"]

    def organizations(self):
        """Read all organization pages without silently selecting an organization."""
        results = []
        for page in range(1, 101):
            data = self._request("GET", "/org/list", query={"pageNum": page, "pageSize": 100})
            rows = self._rows(data)
            results.extend(rows)
            pages = data.get("pages")
            if type(pages) is not int or pages < 0:
                raise GDMSProtocolError("GDMS organization pagination is invalid.")
            if page >= pages:
                return results
        raise GDMSProtocolError("GDMS organization pagination exceeded the limit.")

    @staticmethod
    def _rows(data):
        if not isinstance(data, dict) or not isinstance(data.get("result"), list):
            raise GDMSProtocolError("GDMS list response is invalid.")
        if any(not isinstance(row, dict) for row in data["result"]):
            raise GDMSProtocolError("GDMS list contains an invalid entry.")
        return data["result"]

    def sites(self, org_id):
        return self._rows(self._request("GET", "/site/list", query={"orgId": positive_id(org_id)}))

    def device(self, mac, org_id):
        """Inventory lookup; does not trigger live diagnostics or changes."""
        mac = normalize_mac(mac)
        data = self._request("POST", "/device/list", data={
            "mac": wire_mac(mac), "orgId": positive_id(org_id), "pageNum": 1, "pageSize": 100,
        })
        matches = []
        for row in self._rows(data):
            try:
                matches_mac = normalize_mac(row.get("mac", "")) == mac
            except (ValueError, AttributeError):
                raise GDMSProtocolError("GDMS returned an invalid device identity.") from None
            if matches_mac:
                if row.get("orgId") != positive_id(org_id):
                    raise GDMSProtocolError("GDMS returned a device in another organization.")
                matches.append(row)
        pages = data.get("pages", 1)
        if type(pages) is not int or pages < 0 or len(matches) > 1 or pages > 1:
            raise GDMSProtocolError("GDMS device lookup is ambiguous.")
        return matches[0] if matches else None

    def add_device(self, *, mac, serial, device_name, org_id, site_id):
        if not re.fullmatch(r"[A-Za-z0-9]{1,64}", serial):
            raise ValueError("Enter the serial number from the device label.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device_name):
            raise ValueError("Use a neutral device identifier for GDMS.")
        data = self._request("POST", "/device/add", data=[{
            "mac": wire_mac(mac), "sn": serial, "deviceName": device_name,
            "orgId": positive_id(org_id), "siteId": positive_id(site_id),
        }])
        # retCode=0 does NOT imply enrollment succeeded; inspect batch results.
        if not isinstance(data, dict) or data.get("total") != 1:
            raise GDMSProtocolError("GDMS enrollment response is invalid.")
        if data.get("success") != 1 or data.get("failure") != 0 or data.get("errorDeviceList"):
            raise GDMSError("GDMS did not enroll the device. Check its identity and existing ownership.")
        return data

    def upgrade(self, *, mac, org_id, task_name, firmware_url):
        url = urlsplit(firmware_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
            raise ValueError("Firmware must use a credential-free HTTPS URL.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", task_name):
            raise ValueError("Use a neutral, unique firmware task name.")
        data = self._request("POST", "/task/add", data={
            "taskName": task_name, "taskType": 3, "macList": [wire_mac(mac)],
            "execType": 1, "firmwareDownloadUrl": firmware_url, "orgId": positive_id(org_id),
        })
        if not isinstance(data, dict) or type(data.get("taskId")) is not int or data["taskId"] <= 0:
            raise GDMSProtocolError("GDMS did not return a firmware task identifier.")
        return data["taskId"]

    @sensitive_variables()
    def configure_xml(self, *, mac, org_id, xml):
        if not isinstance(xml, bytes) or not xml or len(xml) > 256 * 1024:
            raise ValueError("Provide a nonempty XML byte string up to 256 KiB.")
        return self._request("POST", "/device/config/xml", form={
            "mac": wire_mac(mac), "orgId": str(positive_id(org_id)), "applyConfig": "true",
        }, xml=xml)

    def live_device(self, mac, *, first):
        """Start a fresh read, then poll within one minute. Inventory is cached.

        The initial response is deliberately ignored; only the following poll
        may establish a firmware observation for this request cycle.
        """
        data = self._request("POST", "/device/detail", data={
            "mac": wire_mac(mac), "isFirst": 1 if first else 0,
        })
        if first or data in (None, "", {}):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("device"), dict):
            raise GDMSProtocolError("GDMS live device response is invalid.")
        device = data["device"]
        try:
            matches = normalize_mac(device.get("mac", "")) == normalize_mac(mac)
        except (ValueError, AttributeError):
            matches = False
        if not matches:
            raise GDMSProtocolError("GDMS live device identity does not match.")
        return device
