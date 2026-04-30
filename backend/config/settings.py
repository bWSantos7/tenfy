"""
Django settings for Tennis Hub.
Production-ready configuration with security best practices.
"""
from pathlib import Path
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured
from decouple import config, Csv, UndefinedValueError
import dj_database_url
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def _require(key: str) -> str:
    """Return env var value or raise ImproperlyConfigured — never falls back to an insecure default."""
    try:
        return config(key)
    except UndefinedValueError:
        raise ImproperlyConfigured(
            f"Required environment variable '{key}' is not set. "
            f"Add it to your .env file or Railway service variables."
        )


# Security — no insecure defaults for critical keys
_raw_secret = _require('SECRET_KEY')
if len(_raw_secret) < 50:
    raise ImproperlyConfigured(
        'SECRET_KEY must be at least 50 characters long. '
        'Generate a strong key with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
    )
SECRET_KEY = _raw_secret
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())
# Railway internal healthcheck always uses this hostname regardless of the public domain
if 'healthcheck.railway.app' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = list(ALLOWED_HOSTS) + ['healthcheck.railway.app']
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:5173',
    cast=Csv()
)

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'django_celery_beat',
    'django_celery_results',
    'cloudinary_storage',
    'cloudinary',
]

LOCAL_APPS = [
    'apps.core',
    'apps.accounts',
    'apps.players',
    'apps.sources',
    'apps.tournaments',
    'apps.eligibility',
    'apps.watchlist',
    'apps.alerts',
    'apps.ingestion',
    'apps.audit',
    'apps.admin_panel',
    'apps.marketplace',
    'apps.registrations',
    'apps.billing',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.RequestLoggingMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database — PostgreSQL only; SQLite is never allowed in any environment
_DATABASE_URL = config('DATABASE_URL', default=None)
if not _DATABASE_URL:
    raise ImproperlyConfigured(
        "DATABASE_URL is required and must point to a PostgreSQL database. "
        "Example: postgresql://user:password@host:5432/dbname"
    )
if _DATABASE_URL.startswith('sqlite'):
    raise ImproperlyConfigured(
        "SQLite is not supported. Set DATABASE_URL to a PostgreSQL connection string."
    )
DATABASES = {
    'default': dj_database_url.parse(
        _DATABASE_URL,
        conn_max_age=600,
        ssl_require=not DEBUG,
    )
}

# Password validation - Argon2 as primary hasher
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTH_USER_MODEL = 'accounts.User'

# Internationalization
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS — specific origins only; no wildcards in production
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:5173,http://localhost:3000',
    cast=Csv()
)
CORS_ALLOW_CREDENTIALS = True
# Regex patterns restricted to known dev ports and trusted deployment domains only.
# IP-range patterns are intentionally removed — they allowed CORS from any LAN machine.
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://localhost:(3000|5173|8081|19000|19006)$",
    r"^http://127\.0\.0\.1:(3000|5173|8081|19000|19006)$",
    # Locked to the specific Railway subdomain — prevents other Railway tenants from matching
    r"^https://tournamenthub-production\.up\.railway\.app$",
    # Production domains — tennis.app.br
    r"^https://(api|www|app)\.tennis\.app\.br$",
]

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'apps.core.pagination.StandardPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/minute',
        'user': '300/minute',
        'heavy_user': '30/minute',
        'heavy_anon': '10/minute',
        'token_refresh': '20/hour',
        'webhook': '120/minute',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# JWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(
        minutes=config('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', default=60, cast=int)
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        days=config('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7, cast=int)
    ),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# Redis / Cache
REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'RETRY_ON_TIMEOUT': True,
            'IGNORE_EXCEPTIONS': True,  # cache misses degrade gracefully
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 30,  # supports 3,000 users with connection reuse
            },
        },
        'KEY_PREFIX': 'thub',
        'TIMEOUT': 300,  # default 5min TTL
    }
}

# Session in DB (safer) but allow Redis fallback
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'default'
CELERY_TIMEZONE = TIME_ZONE
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60       # hard kill after 30 min
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # SoftTimeLimitExceeded raised at 25 min
CELERY_WORKER_MAX_TASKS_PER_CHILD = 50  # recycle worker after 50 tasks (prevent memory leaks)

# Email — uses Resend API when RESEND_API_KEY is set, falls back to console in dev
RESEND_API_KEY = config('RESEND_API_KEY', default='')

if RESEND_API_KEY:
    EMAIL_BACKEND = 'config.email_backend.ResendEmailBackend'
elif DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    # Production without Resend key: fail loudly so emails are never silently dropped
    raise ImproperlyConfigured(
        'RESEND_API_KEY is required in production. '
        'Set it in Railway Variables. Without it, OTP/password reset emails will never reach users.'
    )

DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='no-reply@tournamenthub.app')

# Resend-specific from address.
# If domain is not verified in Resend, set this to: onboarding@resend.dev
# Once tournamenthub.app domain is verified in Resend dashboard, set to: no-reply@tournamenthub.app
RESEND_FROM_EMAIL = config('RESEND_FROM_EMAIL', default=DEFAULT_FROM_EMAIL)

# Security settings (production)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Content-Security-Policy — tightened for API-only backend
CSP_DEFAULT_SRC = ("'none'",)
CSP_FRAME_ANCESTORS = ("'none'",)

if not DEBUG:
    # Railway terminates SSL at the proxy level, so SECURE_SSL_REDIRECT must stay False
    # on Railway. Set SECURE_SSL_REDIRECT=True only when running behind no proxy.
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Scraper config
SCRAPER_USER_AGENT = config(
    'SCRAPER_USER_AGENT',
    default='TennisHubBot/1.0'
)
SCRAPER_TIMEOUT = config('SCRAPER_TIMEOUT', default=30, cast=int)
SCRAPER_RATE_LIMIT_SECONDS = config('SCRAPER_RATE_LIMIT_SECONDS', default=2, cast=int)

FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:5173')

# Import API token — used by n8n / external pipelines to authenticate against
# the federation entry import endpoint without needing a user account.
# Set IMPORT_API_TOKEN in Railway Variables (generate with: python -c "import secrets; print(secrets.token_hex(32))")
# Never expose this token in mobile/frontend code.
IMPORT_API_TOKEN = config('IMPORT_API_TOKEN', default='')

# ── COSAT MongoDB (external crawler service) ─────────────────────────────────
# The COSAT scraper runs as a separate Railway service (bWSantos7/crawler.git)
# and writes tournament/player/ranking data to a dedicated MongoDB.
# This backend reads from that MongoDB and normalizes into PostgreSQL.
# Configure via Railway Variables — never hardcode credentials.
COSAT_MONGO_ENABLED = config('COSAT_MONGO_ENABLED', default=False, cast=bool)
COSAT_MONGO_URL = config('COSAT_MONGO_URL', default='')
COSAT_MONGO_DB = config('COSAT_MONGO_DB', default='cosat_db')
COSAT_MONGO_COLLECTION_TOURNAMENTS = config('COSAT_MONGO_COLLECTION_TOURNAMENTS', default='tournaments')
COSAT_MONGO_COLLECTION_ENTRIES = config('COSAT_MONGO_COLLECTION_ENTRIES', default='players')
COSAT_MONGO_COLLECTION_RANKINGS = config('COSAT_MONGO_COLLECTION_RANKINGS', default='rankingentries')
COSAT_MONGO_CONNECT_TIMEOUT_MS = config('COSAT_MONGO_CONNECT_TIMEOUT_MS', default=5000, cast=int)

# Web Push (VAPID) — generate keys with: python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print(v.private_key, v.public_key)"
VAPID_PRIVATE_KEY = config('VAPID_PRIVATE_KEY', default='')
VAPID_PUBLIC_KEY = config('VAPID_PUBLIC_KEY', default='')
VAPID_CLAIMS_EMAIL = config('VAPID_CLAIMS_EMAIL', default='')

# Asaas payment gateway
ASAAS_API_KEY       = config('ASAAS_API_KEY', default='')
ASAAS_ENVIRONMENT   = config('ASAAS_ENVIRONMENT', default='sandbox')
ASAAS_WEBHOOK_TOKEN = config('ASAAS_WEBHOOK_TOKEN', default='')

# Media files (avatars etc.)
# Set CLOUDINARY_URL=cloudinary://api_key:api_secret@cloud_name in .env / Railway vars
CLOUDINARY_URL = config('CLOUDINARY_URL', default='')
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
if CLOUDINARY_URL:
    # Expose to env so the cloudinary SDK and django-cloudinary-storage both pick it up
    os.environ['CLOUDINARY_URL'] = CLOUDINARY_URL
    # Use custom storage class that injects f_auto,q_auto into every served URL
    # to enable automatic WebP conversion and lossy compression on Cloudinary CDN.
    DEFAULT_FILE_STORAGE = 'apps.core.cloudinary_storage.OptimizedCloudinaryStorage'
    CLOUDINARY_STORAGE = {
        'TRANSFORMATION': [{'quality': 'auto', 'fetch_format': 'auto'}],
    }

# DRF Spectacular
SPECTACULAR_SETTINGS = {
    'TITLE': 'Tennis Hub API',
    'DESCRIPTION': 'Agregador de torneios de tênis centrado no jogador',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Logging
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'app.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

# Sentry — set SENTRY_DSN in Railway vars to enable error monitoring
SENTRY_DSN = config('SENTRY_DSN', default='')
SENTRY_ENVIRONMENT = config('SENTRY_ENVIRONMENT', default='production' if not DEBUG else 'development')
SENTRY_RELEASE = config('SENTRY_RELEASE', default='')

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    import logging as _logging
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        release=SENTRY_RELEASE or None,
        integrations=[
            DjangoIntegration(transaction_style='url'),
            CeleryIntegration(),
            LoggingIntegration(level=_logging.INFO, event_level=_logging.ERROR),
        ],
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.05, cast=float),
        send_default_pii=False,
        attach_stacktrace=True,
    )
