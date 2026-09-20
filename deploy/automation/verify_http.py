"""Anonymous checks only; no family data or response bodies are logged."""

import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def status(url, headers=None):
    try:
        with urlopen(Request(url, headers=headers or {}), timeout=5) as response:
            return response.status, response.headers
    except HTTPError as error:
        return error.code, error.headers


def verify(public_host):
    for path, expected in (("/welcome/", 200), ("/accounts/login/", 200),
                           ("/admin", 404), ("/admin/", 404), ("/admin/login/", 404)):
        code, headers = status("http://public-ingress:8080" + path, {
            "Host": public_host, "X-Forwarded-Proto": "https",
        })
        if code != expected:
            raise RuntimeError("Unexpected public response")
        if expected == 200 and not {"private", "no-store"} <= {
            item.strip() for item in headers.get("Cache-Control", "").split(",")
        }:
            raise RuntimeError("Public HTML caching policy failed")


if __name__ == "__main__":
    # Only this non-secret value is read from an operator-owned JSON file.
    import json
    import sys
    from pathlib import Path
    from urllib.parse import urlsplit

    url = json.loads(Path("/policy/http.json").read_text())["public_url"].rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.path:
        raise ValueError("Expected an HTTPS origin")
    for attempt in range(30):
        try:
            if sys.argv[1:] == ["private"]:
                # A rejected Host still proves the private Gunicorn listener is up.
                if status("http://web:8000/admin/login/")[0] not in (200, 400):
                    raise RuntimeError("Private application unavailable")
            elif sys.argv[1:] == ["public"]:
                verify(parsed.netloc)
            else:
                raise ValueError("Expected private or public probe")
            break
        except (RuntimeError, URLError, TimeoutError):
            if attempt == 29:
                raise
            time.sleep(3)
    print("Anonymous application checks passed.")
