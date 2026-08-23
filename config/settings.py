"""
Django settings for NurFX.ai — production-hardened configuration.
"""
from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    JWT_ACCESS_TOKEN_LIFETIME_MINUTES=(int, 15),
    JWT_REFRESH_TOKEN_LIFETIME_DAYS=(int, 7),
    SECURE_SSL_REDIRECT=(bool, True),
    SESSION_COOKIE_SECURE=(bool, True),
    CSRF_COOKIE_SECURE=(bool, True),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Admin panel path — override in production to a non-default, hard-to-guess
# value (e.g. "secure-panel-x7f2/") so it isn't a predictable scan target.
DJANGO_ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/")

# A malformed value here breaks the import of urls.py, which takes down every
# endpoint — not just the admin — with a traceback that points at Django's URL
# resolver rather than at .env. Fail with the actual cause instead.
if "<" in DJANGO_ADMIN_URL or ">" in DJANGO_ADMIN_URL:
    raise ImproperlyConfigured(
        f"DJANGO_ADMIN_URL is {DJANGO_ADMIN_URL!r} — the angle brackets are "
        "placeholder syntax from .env.example. Set a real path, e.g. "
        "DJANGO_ADMIN_URL=nurfx-panel-7x2f/"
    )
if not DJANGO_ADMIN_URL.endswith("/"):
    raise ImproperlyConfigured(
        f"DJANGO_ADMIN_URL is {DJANGO_ADMIN_URL!r} — it must end with '/'."
    )

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    # NurFX apps
    "apps.authentication",
    "apps.analysis",
    "apps.tokens",
    "apps.ai_engine",
    "apps.bot",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Required for RATELIMIT_VIEW below to run; without it a blocked request
    # falls through as a plain HTML 403 instead of the JSON 429.
    "django_ratelimit.middleware.RatelimitMiddleware",
]

ROOT_URLCONF = "config.urls"
RATELIMIT_VIEW = "apps.authentication.ratelimit_handlers.ratelimit_handler"

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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database — parametrized ORM only (no raw SQL)
# ---------------------------------------------------------------------------
DATABASES = {
    # No insecure fallback — fail fast at startup if not explicitly configured.
    "default": env.db("DATABASE_URL"),
}

# ---------------------------------------------------------------------------
# Custom User Model
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "authentication.User"

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & Media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# OWASP Security Headers
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT") and not DEBUG

# Gunicorn only ever sees plain HTTP from nginx, so without this Django judges
# every request insecure and SECURE_SSL_REDIRECT bounces it to HTTPS forever.
# Only safe because nothing but the local reverse proxy can reach port 8000 —
# it is bound to 127.0.0.1 in docker-compose.yml. Set the header in nginx with
# `proxy_set_header X-Forwarded-Proto $scheme;` so a client cannot forge it.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_HSTS_SECONDS = 31_536_000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = env("SESSION_COOKIE_SECURE") and not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = env("CSRF_COOKIE_SECURE") and not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# ---------------------------------------------------------------------------
# CORS — whitelisted origins only (never *)
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list(
    "DJANGO_CORS_ALLOWED_ORIGINS",
    default=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
)
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=CORS_ALLOWED_ORIGINS,
)

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.authentication.authentication.CookieJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/minute",
        "user": "60/minute",
        "auth": "5/minute",
        "analysis": "5/minute",
        "coupon": "10/minute",
    },
    "EXCEPTION_HANDLER": "apps.authentication.exceptions.custom_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "NurFX.ai Backend API",
    "DESCRIPTION": "Production-grade Forex AI analysis, authentication, and token management API.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
    },
    # Security: Restrict Swagger & ReDoc API docs to staff/admin in production to prevent security mapping scans
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"] if not DEBUG else ["rest_framework.permissions.AllowAny"],
}

# ---------------------------------------------------------------------------
# SimpleJWT — short-lived access tokens
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env("JWT_ACCESS_TOKEN_LIFETIME_MINUTES")),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env("JWT_REFRESH_TOKEN_LIFETIME_DAYS")),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_COOKIE": "access_token",
    "AUTH_COOKIE_SECURE": not DEBUG,
    "AUTH_COOKIE_HTTP_ONLY": True,
    "AUTH_COOKIE_SAMESITE": "Lax",
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=DEBUG)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 600  # 10 min max per AI pipeline task

# ---------------------------------------------------------------------------
# Redis (rate-limit cache backend)
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/2"),
    }
}

# ---------------------------------------------------------------------------
# NurFX Business Constants
# ---------------------------------------------------------------------------
NURFX_ANALYSIS_TOKEN_COST = 3
NURFX_WELCOME_TOKENS = 6
NURFX_BASE_TOKEN_VALUE_UZS = 8_000

NURFX_SUBSCRIPTION_PACKAGES = {
    "BASIC": {"tokens": 30, "price_uzs": 210_000, "price_per_token": 7_000},
    "PRO": {"tokens": 90, "price_uzs": 540_000, "price_per_token": 6_000},
    "VIP_MAX": {"tokens": 210, "price_uzs": 1_197_000, "price_per_token": 5_700},
}

# Payment details are personal data (card number, legal name) — they belong in
# .env, never in a committed default.
NURFX_PAYMENT_CARD_NUMBER = env("NURFX_PAYMENT_CARD_NUMBER", default="")
NURFX_PAYMENT_CARD_HOLDER = env("NURFX_PAYMENT_CARD_HOLDER", default="")
NURFX_ADMIN_TELEGRAM_USERNAME = env("NURFX_ADMIN_TELEGRAM_USERNAME", default="")

# ---------------------------------------------------------------------------
# External API Keys (never hardcoded — loaded from env)
# ---------------------------------------------------------------------------
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", default="")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_ADMIN_IDS = env.list("TELEGRAM_ADMIN_IDS", default=[])

# ---------------------------------------------------------------------------
# AI engine — one Claude Opus 5 vision call per analysis
# ---------------------------------------------------------------------------
AI_CLAUDE_MODEL = env("AI_CLAUDE_MODEL", default="claude-opus-5")
AI_CLAUDE_MAX_TOKENS = env.int("AI_CLAUDE_MAX_TOKENS", default=16_000)

# low | medium | high | xhigh | max. Effort trades intelligence against tokens
# and latency; sweep it against your own results rather than assuming higher is
# better. `xhigh` is worth testing for charts the model finds ambiguous.
AI_CLAUDE_EFFORT = env("AI_CLAUDE_EFFORT", default="high")

# Server-side fallback re-runs a request another model refused, instead of
# failing the analysis. Chart analysis rarely trips safety classifiers, so turn
# this off if the beta parameter ever starts rejecting requests.
AI_ENABLE_REFUSAL_FALLBACK = env.bool("AI_ENABLE_REFUSAL_FALLBACK", default=True)

# Image upload limits
MAX_CHART_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_CHART_IMAGE_PIXELS = 25_000_000  # 25 MP — blocks decompression-bomb uploads
# Opus 5 reads images up to 2576px on the long edge; anything larger is spent
# on bytes the model never sees.
MAX_CHART_IMAGE_LONG_EDGE = 2576
ALLOWED_CHART_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
