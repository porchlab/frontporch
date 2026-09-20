import json
import os
import re
import subprocess
import sys

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from directory.models import Family, Parent


@override_settings(
    ROOT_URLCONF="frontporch.public_urls",
    FRONTPORCH_ALLOW_REGISTRATION=True,
    FRONTPORCH_PUBLIC_URL="https://front.porchlab.app",
    ALLOWED_HOSTS=["front.porchlab.app"],
    CSRF_TRUSTED_ORIGINS=["https://front.porchlab.app"],
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    MIDDLEWARE=[
        *settings.MIDDLEWARE,
        "frontporch.middleware.PrivateResponseMiddleware",
    ],
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class PublicPortalTests(TestCase):
    def setUp(self):
        self.client = Client(
            HTTP_HOST="front.porchlab.app", HTTP_X_FORWARDED_PROTO="https"
        )

    def test_admin_routes_are_absent_even_for_superusers(self):
        user = User.objects.create_superuser("operator", "op@example.com", "test-pass")
        self.client.force_login(user)
        for path in ("/admin/", "/admin/login/", "/admin/auth/user/", "/admin"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_public_registration_cannot_create_an_account(self):
        for method in (self.client.get, self.client.post):
            self.assertEqual(method("/register/").status_code, 404)
        self.assertEqual(User.objects.count(), 0)

    def test_existing_family_can_invite_and_recipient_can_register_publicly(self):
        family = Family.objects.create(name="Maple")
        user = User.objects.create_user("guardian", "maple@example.com", "test-pass")
        Parent.objects.create(user=user, family=family, display_name="Taylor")
        self.client.force_login(user)
        self.assertEqual(
            self.client.post(
                reverse("directory:family_invite"), {"email": "new@example.com"}
            ).status_code,
            302,
        )
        token = re.search(
            r"https://front\.porchlab\.app/register/([^/]+)/", mail.outbox[-1].body
        ).group(1)
        self.client.logout()
        recipient = Client(
            enforce_csrf_checks=True,
            HTTP_HOST="front.porchlab.app",
            HTTP_X_FORWARDED_PROTO="https",
        )
        url = reverse("directory:register_invited", args=[token])
        page = recipient.get(url)
        self.assertEqual(page.headers["Referrer-Policy"], "same-origin")
        response = recipient.post(
            url,
            {
                "family_name": "Willow",
                "display_name": "Morgan",
                "password1": "different-test-pass-123",
                "password2": "different-test-pass-123",
                "csrfmiddlewaretoken": recipient.cookies[settings.CSRF_COOKIE_NAME].value,
            },
            HTTP_ORIGIN="https://front.porchlab.app",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("directory:dashboard"))
        self.assertTrue(User.objects.filter(email="new@example.com").exists())
        self.assertEqual(Family.objects.count(), 2)

    def test_entry_pages_have_no_signup_links_and_are_not_cacheable(self):
        for path in ("/welcome/", "/accounts/login/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'href="/register/"')
            self.assertIn("private", response.headers["Cache-Control"])
            self.assertIn("no-store", response.headers["Cache-Control"])

    def test_family_data_requires_login(self):
        response = self.client.get("/children/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/login/?next=/children/")

    def test_login_accepts_csrf_from_https_origin_and_issues_secure_cookies(self):
        family = Family.objects.create(name="River House")
        user = User.objects.create_user(
            "guardian", email="guardian@example.com", password="test-pass"
        )
        Parent.objects.create(
            user=user, family=family, display_name="Taylor", email=user.email
        )
        client = Client(
            enforce_csrf_checks=True,
            HTTP_HOST="front.porchlab.app",
            HTTP_X_FORWARDED_PROTO="https",
        )
        page = client.get(reverse("login"))
        csrf_cookie = page.cookies[settings.CSRF_COOKIE_NAME]
        self.assertTrue(csrf_cookie["secure"])
        response = client.post(
            reverse("login"),
            {
                "username": user.email,
                "password": "test-pass",
                "csrfmiddlewaretoken": csrf_cookie.value,
            },
            HTTP_ORIGIN="https://front.porchlab.app",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]["secure"])
        self.assertEqual(client.get("/children/").status_code, 200)

    def test_csrf_rejects_other_origins(self):
        client = Client(
            enforce_csrf_checks=True,
            HTTP_HOST="front.porchlab.app",
            HTTP_X_FORWARDED_PROTO="https",
        )
        client.get(reverse("login"))
        response = client.post(
            reverse("login"),
            {"csrfmiddlewaretoken": client.cookies[settings.CSRF_COOKIE_NAME].value},
            HTTP_ORIGIN="https://untrusted.example.com",
        )
        self.assertEqual(response.status_code, 403)

    def test_untrusted_host_is_rejected(self):
        self.assertEqual(
            self.client.get("/welcome/", HTTP_HOST="vault.example.com").status_code, 400
        )

    def test_http_redirects_and_forwarded_https_does_not_loop(self):
        response = self.client.get("/welcome/", HTTP_X_FORWARDED_PROTO="http")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "https://front.porchlab.app/welcome/")
        self.assertEqual(self.client.get("/welcome/").status_code, 200)


class PublicSettingsTests(SimpleTestCase):
    def test_public_process_enforces_security_even_with_private_environment(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json; from django.conf import settings as s; "
                "print(json.dumps({k: getattr(s, k) for k in "
                "['DEBUG', 'ALLOWED_HOSTS', 'SECURE_SSL_REDIRECT', "
                "'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', "
                "'SECURE_PROXY_SSL_HEADER', 'SESSION_COOKIE_NAME', "
                "'ROOT_URLCONF', 'FRONTPORCH_ALLOW_REGISTRATION', 'FRONTPORCH_PUBLIC_URL']}))",
            ],
            env={
                **os.environ,
                "DJANGO_SETTINGS_MODULE": "frontporch.public_settings",
                "DJANGO_SECRET_KEY": "test-only-public-portal-key-" * 3,
                "DJANGO_DEBUG": "true",
                "DJANGO_ALLOWED_HOSTS": "*",
                "FRONTPORCH_PUBLIC_HOST": "front.porchlab.app",
                "FRONTPORCH_PUBLIC_URL": "http://private.example.com:8000",
            },
            capture_output=True,
            text=True,
            check=True,
        )
        config = json.loads(result.stdout)
        self.assertFalse(config["DEBUG"])
        self.assertEqual(config["ALLOWED_HOSTS"], ["front.porchlab.app"])
        for name in (
            "SECURE_SSL_REDIRECT",
            "SESSION_COOKIE_SECURE",
            "CSRF_COOKIE_SECURE",
        ):
            self.assertTrue(config[name])
        self.assertEqual(
            config["SECURE_PROXY_SSL_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"]
        )
        self.assertEqual(config["SESSION_COOKIE_NAME"], "__Host-frontporch_session")
        self.assertEqual(config["ROOT_URLCONF"], "frontporch.public_urls")
        self.assertTrue(config["FRONTPORCH_ALLOW_REGISTRATION"])
        self.assertEqual(config["FRONTPORCH_PUBLIC_URL"], "https://front.porchlab.app")
