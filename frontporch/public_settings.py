"""Settings for the isolated, HTTPS-only parent portal behind public-ingress."""

import re

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("The public portal requires a strong DJANGO_SECRET_KEY.")

DEBUG = False
ROOT_URLCONF = "frontporch.public_urls"
PUBLIC_HOST = os.environ.get("FRONTPORCH_PUBLIC_HOST", "front.porchlab.app")
if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", PUBLIC_HOST):
    raise ImproperlyConfigured("FRONTPORCH_PUBLIC_HOST must be one DNS hostname.")
ALLOWED_HOSTS = [PUBLIC_HOST]
CSRF_TRUSTED_ORIGINS = [f"https://{PUBLIC_HOST}"]
FRONTPORCH_PUBLIC_URL = f"https://{PUBLIC_HOST}"

# Only public-ingress can reach this listener from the tunnel network. It
# overwrites forwarded headers; never publish this container's port on the host.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_SSL_HOST = PUBLIC_HOST
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_NAME = "__Host-frontporch_session"
CSRF_COOKIE_NAME = "__Host-frontporch_csrf"
SECURE_REFERRER_POLICY = "same-origin"

# New families need an email-bound invitation from an existing family's guardian.
# The shared registration view enforces invitations on both portal processes.
MIDDLEWARE = [*MIDDLEWARE, "frontporch.middleware.PrivateResponseMiddleware"]
