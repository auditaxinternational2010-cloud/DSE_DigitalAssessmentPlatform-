"""
Django settings for eya_questionnaire project.
"""

import os
import sys
from pathlib import Path
from decouple import config
from django.contrib.messages import constants as _msg

# True while running the Django test suite (DEBUG is forced off in CI/containers).
TESTING = 'test' in sys.argv

MESSAGE_TAGS = {_msg.ERROR: 'danger'}

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1','dolphin-app-u6d77.ondigitalocean.app', cast=lambda v: [s.strip() for s in v.split(',')])

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
    'crispy_forms',
    'crispy_bootstrap5',
    'django_filters',
]

LOCAL_APPS = [
    'accounts',
    'assessment',
    'audit',
    'share',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS + [
    'django_cleanup.apps.CleanupConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'accounts.middleware.MustChangePasswordMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'eya_questionnaire.urls'

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
                'accounts.context_processors.eya_nav',
            ],
        },
    },
]

WSGI_APPLICATION = 'eya_questionnaire.wsgi.application'

# Database — uses DATABASE_URL when provided (DigitalOcean), individual vars otherwise (local)
_DATABASE_URL = config('DATABASE_URL', default='')
if _DATABASE_URL:
    import dj_database_url
    DATABASES = {'default': dj_database_url.parse(_DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='eya_questionnaire'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default='postgres'),
            'HOST': config('DB_HOST', default='db'),
            'PORT': config('DB_PORT', default='5432'),
            'CONN_MAX_AGE': config('CONN_MAX_AGE', default=600, cast=int),
            'CONN_HEALTH_CHECKS': True,
        }
    }

# Cache — shared Redis in prod (used by rate limiting). Falls back to per-process
# local memory when REDIS_URL is unset, so local dev and the test suite work unchanged.
_REDIS_URL = config('REDIS_URL', default='')
if _REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': _REDIS_URL,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    {
        'NAME': 'accounts.validators.ComplexPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Evidence upload limits (override via .env)
EVIDENCE_MAX_FILE_BYTES     = config('EVIDENCE_MAX_FILE_BYTES',     default=5   * 1024 * 1024, cast=int)
EVIDENCE_MAX_FILES_PER_RESP = config('EVIDENCE_MAX_FILES_PER_RESP', default=5,                 cast=int)
# Per-organization document-library storage quota (was per-questionnaire).
EVIDENCE_MAX_QUOTA_BYTES    = config('EVIDENCE_MAX_QUOTA_BYTES',    default=100 * 1024 * 1024, cast=int)

# A full category submit posts several fields per criterion (score, notes, numeric
# sub-fields, file inputs). Raise the default 1000-field cap to avoid TooManyFieldsSent.
DATA_UPLOAD_MAX_NUMBER_FIELDS = config('DATA_UPLOAD_MAX_NUMBER_FIELDS', default=3000, cast=int)

# Storage backends — Django 4.2+ STORAGES dict (replaces deprecated DEFAULT_FILE_STORAGE / STATICFILES_STORAGE)
# Set DEFAULT_FILE_STORAGE env var in prod to switch to S3/GCS without code changes.
STORAGES = {
    "default": {
        "BACKEND": config(
            'DEFAULT_FILE_STORAGE',
            default='django.core.files.storage.FileSystemStorage',
        ),
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# The test suite must NEVER touch real object storage. Per-test
# @override_settings(DEFAULT_FILE_STORAGE=...) does NOT work: that setting was
# deprecated in Django 4.2 and REMOVED in 5.1, so overriding it is a silent
# no-op and uploads go straight to the production S3 bucket. Forcing it here
# means a new test that forgets the decorator is still safe.
# ('pytest' in sys.modules covers a future pytest runner, where sys.argv has no 'test'.)
if TESTING or 'pytest' in sys.modules:
    STORAGES['default'] = {'BACKEND': 'django.core.files.storage.FileSystemStorage'}
    MEDIA_ROOT = BASE_DIR / 'test_media'

# S3 (only required when DEFAULT_FILE_STORAGE = storages.backends.s3boto3.S3Boto3Storage)
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
# IMPORTANT: AWS_S3_REGION_NAME must match the bucket's actual region. If it is
# empty or wrong, boto3 talks to us-east-1 and S3 answers every request with a
# redirect to the real region — an extra network round trip on every upload and
# download that makes them noticeably slow.
AWS_S3_REGION_NAME      = config('AWS_S3_REGION_NAME',      default='')
AWS_ACCESS_KEY_ID       = config('AWS_ACCESS_KEY_ID',        default='')
AWS_SECRET_ACCESS_KEY   = config('AWS_SECRET_ACCESS_KEY',   default='')
AWS_DEFAULT_ACL         = 'private'
AWS_S3_FILE_OVERWRITE   = False
# Virtual-hosted-style endpoints (bucket.s3.region.amazonaws.com) avoid a redirect
# hop versus the legacy path style and are the recommended default.
AWS_S3_ADDRESSING_STYLE = config('AWS_S3_ADDRESSING_STYLE', default='virtual')
AWS_QUERYSTRING_EXPIRE  = config('AWS_QUERYSTRING_EXPIRE',  default=3600, cast=int)

# GCS (only required when DEFAULT_FILE_STORAGE = storages.backends.gcloud.GoogleCloudStorage)
GS_BUCKET_NAME = config('GS_BUCKET_NAME', default='')
GS_DEFAULT_ACL = 'private'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'

# Abuse protection (override via .env). Counters live in the cache backend.
LOGIN_RATELIMIT_ATTEMPTS = config('LOGIN_RATELIMIT_ATTEMPTS', default=10, cast=int)
LOGIN_RATELIMIT_WINDOW = config('LOGIN_RATELIMIT_WINDOW', default=900, cast=int)        # 15 min
PARTICIPATION_RATELIMIT_ATTEMPTS = config('PARTICIPATION_RATELIMIT_ATTEMPTS', default=10, cast=int)
PARTICIPATION_RATELIMIT_WINDOW = config('PARTICIPATION_RATELIMIT_WINDOW', default=3600, cast=int)  # 1 hr
# Public share-dashboard endpoints. Loose — this blunts token brute-forcing
# without interfering with a page left open on a wall display polling every 60s.
SHARE_RATELIMIT_ATTEMPTS = config('SHARE_RATELIMIT_ATTEMPTS', default=60, cast=int)
SHARE_RATELIMIT_WINDOW = config('SHARE_RATELIMIT_WINDOW', default=60, cast=int)

# CSRF — required for HTTPS in Django 4.0+
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:8000',
    cast=lambda v: [s.strip() for s in v.split(',')],
)

# Tell Django the real scheme when behind DigitalOcean's proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Production security hardening — applied automatically when DEBUG is off
# (but never during the test suite, whose client speaks plain HTTP).
# Each is overridable via .env for environments that need to opt out.
if not DEBUG and not TESTING:
    SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
    CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
    SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
    SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Email — cPanel SMTP, port 465 SSL
EMAIL_BACKEND    = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST       = config('EMAIL_HOST', default='mail.auditaxinternational.co.tz')
EMAIL_PORT       = config('EMAIL_PORT', default=465, cast=int)
EMAIL_USE_SSL    = config('EMAIL_USE_SSL', default=True, cast=bool)
EMAIL_USE_TLS    = False
EMAIL_HOST_USER  = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='EYA Platform <noreply@auditaxinternational.co.tz>')
SITE_URL         = config('SITE_URL', default='http://localhost:8000')

# Comma-separated override. When set, new-participation-request alerts go to
# these addresses INSTEAD of every admin-role user.
ADMIN_NOTIFY_EMAILS = config(
    'ADMIN_NOTIFY_EMAILS', default='',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()],
)
# Without a timeout a hung SMTP connection holds a gunicorn thread for the full
# 120s request timeout. Production has only 12 concurrent slots.
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=10, cast=int)
