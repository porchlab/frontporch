"""Django settings for FrontPorch."""

from pathlib import Path
import os

import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path):
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-frontporch-local-development-only",
)

DEBUG = env_bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

DEFAULT_PHONE_REGION = os.environ.get("FRONTPORCH_DEFAULT_PHONE_REGION", "US")
ASTERISK_GENERATED_CONFIG_DIR = os.environ.get("ASTERISK_GENERATED_CONFIG_DIR", "")
ASTERISK_CUSTOM_SOUNDS_DIR = os.environ.get(
    "ASTERISK_CUSTOM_SOUNDS_DIR",
    str(BASE_DIR / "asterisk" / "sounds"),
)
ASTERISK_OUTBOUND_CALLER_ID = os.environ.get("ASTERISK_OUTBOUND_CALLER_ID", "")
ASTERISK_TTS_ENGINE_SIGNATURE = os.environ.get(
    "ASTERISK_TTS_ENGINE_SIGNATURE",
    "piper-tts-1.7.0_en_US-ljspeech-medium-f5a6e9094787_sox-14.4.2+git20190427-3.5",
)
ASTERISK_TTS_PYTHON_COMMAND = os.environ.get(
    "ASTERISK_TTS_PYTHON_COMMAND",
    "python",
)
ASTERISK_TTS_MODEL_PATH = os.environ.get(
    "ASTERISK_TTS_MODEL_PATH",
    "/opt/frontporch/piper/en_US-ljspeech-medium.onnx",
)
ASTERISK_TTS_SOX_COMMAND = os.environ.get("ASTERISK_TTS_SOX_COMMAND", "sox")
ASTERISK_TTS_VOICE = os.environ.get("ASTERISK_TTS_VOICE", "en_US-ljspeech-medium")
ASTERISK_TTS_LENGTH_SCALE = float(os.environ.get("ASTERISK_TTS_LENGTH_SCALE", "1.0"))
ASTERISK_TTS_NOISE_SCALE = float(os.environ.get("ASTERISK_TTS_NOISE_SCALE", "0.667"))
ASTERISK_TTS_NOISE_W_SCALE = float(os.environ.get("ASTERISK_TTS_NOISE_W_SCALE", "0.8"))
ASTERISK_TTS_RANDOM_SEED = int(os.environ.get("ASTERISK_TTS_RANDOM_SEED", "1729"))
ASTERISK_TTS_VOLUME = float(os.environ.get("ASTERISK_TTS_VOLUME", "1.0"))
ASTERISK_AUTO_APPLY_CONFIG = env_bool("ASTERISK_AUTO_APPLY_CONFIG", default=False)
# Optional GDMS pilot tooling. Empty credentials never enable enrollment or
# initiate requests at application startup. Keep these in the local environment.
GDMS_REGION = os.environ.get("GDMS_REGION", "us")
GDMS_USERNAME = os.environ.get("GDMS_USERNAME", "")
GDMS_PASSWORD = os.environ.get("GDMS_PASSWORD", "")
GDMS_CLIENT_ID = os.environ.get("GDMS_CLIENT_ID", "")
GDMS_CLIENT_SECRET = os.environ.get("GDMS_CLIENT_SECRET", "")
# An empty configuration never starts a VPN service or peer reconciler.
WIREGUARD_ENABLED = env_bool("WIREGUARD_ENABLED", default=False)
WIREGUARD_SERVER_ADDRESS = os.environ.get("WIREGUARD_SERVER_ADDRESS", "")
WIREGUARD_ENCRYPTION_KEY = os.environ.get("WIREGUARD_ENCRYPTION_KEY", "")
WIREGUARD_DESIRED_DIR = os.environ.get("WIREGUARD_DESIRED_DIR", "")
WIREGUARD_OBSERVED_DIR = os.environ.get("WIREGUARD_OBSERVED_DIR", "")
WIREGUARD_NETWORK_FILE = os.environ.get("WIREGUARD_NETWORK_FILE", "")
WIREGUARD_SERVER_PUBLIC_KEY = os.environ.get("WIREGUARD_SERVER_PUBLIC_KEY", "")
WIREGUARD_ENDPOINT = os.environ.get("WIREGUARD_ENDPOINT", "")
ASTERISK_AMI_HOST = os.environ.get("ASTERISK_AMI_HOST", "")
ASTERISK_AMI_PORT = int(os.environ.get("ASTERISK_AMI_PORT", "5038"))
ASTERISK_AMI_USERNAME = os.environ.get("ASTERISK_AMI_USERNAME", "")
ASTERISK_AMI_PASSWORD = os.environ.get("ASTERISK_AMI_PASSWORD", "")
ASTERISK_AMI_TIMEOUT = float(os.environ.get("ASTERISK_AMI_TIMEOUT", "5"))


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "directory",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.apple",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "frontporch.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "directory.context_processors.portal",
            ],
        },
    },
]

WSGI_APPLICATION = "frontporch.wsgi.application"

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required and must point to PostgreSQL.")

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise RuntimeError("FrontPorch only supports PostgreSQL databases.")

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TZ", "America/New_York")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/welcome/"

AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]
ACCOUNT_ADAPTER = "directory.accounts.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "directory.accounts.SocialAccountAdapter"
SOCIALACCOUNT_FORMS = {"signup": "directory.forms.InvitedSocialSignupForm"}
ACCOUNT_LOGIN_METHODS = {"email", "username"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
ACCOUNT_FORMS = {"login": "directory.forms.ParentAuthenticationForm"}
# Existing passwords keep working; invitation acceptance verifies new accounts.
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_CHANGE_EMAIL = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[FrontPorch] "
ACCOUNT_SESSION_REMEMBER = False
ACCOUNT_LOGOUT_ON_GET = False
SOCIALACCOUNT_LOGIN_ON_GET = False
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "OAUTH_PKCE_ENABLED": True,
        "EMAIL_AUTHENTICATION": True,
    },
    "apple": {
        "SCOPE": ["email", "name"],
        "EMAIL_AUTHENTICATION": True,
    },
}

google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
if google_client_id and google_client_secret:
    SOCIALACCOUNT_PROVIDERS["google"]["APP"] = {
        "client_id": google_client_id,
        "secret": google_client_secret,
        "key": "",
    }

apple_client_id = os.environ.get("APPLE_CLIENT_ID", "")
apple_key_id = os.environ.get("APPLE_KEY_ID", "")
apple_team_id = os.environ.get("APPLE_TEAM_ID", "")
apple_private_key = os.environ.get("APPLE_PRIVATE_KEY", "").replace("\\n", "\n")
if apple_client_id and apple_key_id and apple_team_id and apple_private_key:
    SOCIALACCOUNT_PROVIDERS["apple"]["APP"] = {
        "client_id": apple_client_id,
        "secret": apple_key_id,
        "key": apple_team_id,
        "settings": {"certificate_key": apple_private_key},
    }

# Configure SMTP in private deployment settings. No invitation preview tokens are exposed in the portal.
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", False)
EMAIL_USE_SSL = env_bool("DJANGO_EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get(
    "DJANGO_DEFAULT_FROM_EMAIL", "FrontPorch <noreply@example.com>"
)

FRONTPORCH_PUBLIC_URL = os.environ.get("FRONTPORCH_PUBLIC_URL", "").strip()
FRONTPORCH_DEMO_URL = os.environ.get(
    "FRONTPORCH_DEMO_URL", "https://front-demo.porchlab.app/#family/overview"
).strip()
# Enables invited registration only; there is no open signup route.
FRONTPORCH_ALLOW_REGISTRATION = True

# Self-service enrollment is opt-in; provider secrets remain worker-only.
PHONE_ENROLLMENT_ENABLED = env_bool("PHONE_ENROLLMENT_ENABLED", default=False)
GDMS_ORG_ID = os.environ.get("GDMS_ORG_ID", "")
GDMS_SITE_ID = os.environ.get("GDMS_SITE_ID", "")
PHONE_PROFILE_PUBLIC_URL = os.environ.get("PHONE_PROFILE_PUBLIC_URL", "")
PHONE_PROFILE_DIR = os.environ.get("PHONE_PROFILE_DIR", "")
PHONE_RECEIPT_DIR = os.environ.get("PHONE_RECEIPT_DIR", "")
WP816_FIRMWARE_URL = os.environ.get("WP816_FIRMWARE_URL", "")
# Preserve the reviewed pilot release for deployments without an override.
# A different version must supply its own checksum; never reuse the pilot hash.
WP816_FIRMWARE_VERSION = os.environ.get("WP816_FIRMWARE_VERSION", "") or "1.0.3.39"
WP816_FIRMWARE_SHA256 = os.environ.get("WP816_FIRMWARE_SHA256", "") or (
    "591babdf593e084a7d398740cf9d35bf446fcaae96f30235781e7cca64d59be9"
    if WP816_FIRMWARE_VERSION == "1.0.3.39" else ""
)
