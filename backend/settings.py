from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()
import sys
import dj_database_url
from urllib.parse import urlparse

# ─── Base ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-temp-secret')
DEBUG = os.getenv('DEBUG', 'True').lower() in ('1', 'true', 'yes')


def _split_env_list(name):
    return [item.strip() for item in os.getenv(name, '').split(',') if item.strip()]


def _env_value(*names, default=''):
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return default


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _normalize_origin(value):
    value = (value or '').strip()
    if not value:
        return ''
    if '://' not in value:
        value = f'https://{value}'
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return ''
    return f'{parsed.scheme}://{parsed.netloc}'

if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = _split_env_list('ALLOWED_HOSTS')

extra_hosts = []
for env_name in ('RENDER_EXTERNAL_HOSTNAME', 'RAILWAY_PUBLIC_DOMAIN'):
    extra_hosts.extend(_split_env_list(env_name))

for env_name in ('APP_URL', 'PUBLIC_URL', 'RENDER_EXTERNAL_URL'):
    parsed = urlparse(os.getenv(env_name, '').strip())
    if parsed.hostname:
        extra_hosts.append(parsed.hostname)

ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS + extra_hosts))

# ─── Apps ────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # third party
    'rest_framework',
    'corsheaders',
    # your apps
    'users',
]

# ─── Custom User ─────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'users.User'

# ─── Middleware ───────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'users.middleware.NoStoreAuthenticatedPagesMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'users.middleware.InactivityTimeoutMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

# ─── Templates ───────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

# ─── Database ─────────────────────────────────────────────────────────────────
DATABASES = {}
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    if DATABASE_URL.startswith('sqlite'):
        DATABASES['default'] = dj_database_url.parse(DATABASE_URL)
    else:
        DATABASES['default'] = dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=not DEBUG,
        )
else:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', ''),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }

# ─── Password Validation ──────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── REST Framework ───────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',
    ),
}

# ─── CORS ─────────────────────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True

# ─── CSRF / Proxy / Cookies ──────────────────────────────────────────────────
csrf_trusted_origins = [
    _normalize_origin(origin)
    for origin in _split_env_list('CSRF_TRUSTED_ORIGINS')
]

for env_name in ('APP_URL', 'PUBLIC_URL', 'RENDER_EXTERNAL_URL'):
    origin = _normalize_origin(os.getenv(env_name, ''))
    if origin:
        csrf_trusted_origins.append(origin)

CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(origin for origin in csrf_trusted_origins if origin))

# Trust HTTPS forwarded by platforms like Render/Railway/Nginx so CSRF checks
# see the original secure origin instead of the internal Gunicorn HTTP request.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# ─── Internationalisation ─────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'Asia/Kolkata'
USE_I18N      = True
USE_TZ        = True

# ─── Static Files ─────────────────────────────────────────────────────────────
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ─── Media Files (uploads) ────────────────────────────────────────────────────
# Use Railway persistent volumes - no AWS needed
# Check for Railway persistent volume mount, otherwise use local media directory
MEDIA_URL  = '/media/'
# For Railway: mount the persistent volume at /app/media
# For local development: creates media/ folder in project root
_media_root_env = os.getenv('MEDIA_ROOT', '')
if _media_root_env:
    MEDIA_ROOT = _media_root_env
else:
    MEDIA_ROOT = BASE_DIR / 'media'
    
# Ensure MEDIA_ROOT directory exists
os.makedirs(MEDIA_ROOT, exist_ok=True)

# ─── Campus Settings ──────────────────────────────────────────────────────────
ALLOWED_EMAIL_DOMAIN = '@iitk.ac.in'  # replace with your college domain

# Google Maps (Geocoding) API key for generating map links
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '')
# Razorpay Payment Gateway
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', '')

RESEND_API_KEY = _env_value('RESEND_API_KEY')
EMAIL_BACKEND = _env_value(
    'EMAIL_BACKEND',
    default='users.email_backends.ResendEmailBackend' if RESEND_API_KEY else 'django.core.mail.backends.smtp.EmailBackend',
)
if RESEND_API_KEY and EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend':
    EMAIL_BACKEND = 'users.email_backends.ResendEmailBackend'
EMAIL_HOST = _env_value('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = int(_env_value('EMAIL_PORT', default='587'))
EMAIL_USE_SSL = _env_bool('EMAIL_USE_SSL', default=False)
EMAIL_USE_TLS = _env_bool('EMAIL_USE_TLS', default=not EMAIL_USE_SSL)
EMAIL_HOST_USER = _env_value('EMAIL_HOST_USER', 'EMAIL_USER')
EMAIL_HOST_PASSWORD = _env_value('EMAIL_HOST_PASSWORD', 'EMAIL_PASSWORD')
if EMAIL_HOST.endswith('gmail.com'):
    EMAIL_HOST_PASSWORD = EMAIL_HOST_PASSWORD.replace(' ', '')
DEFAULT_FROM_EMAIL = _env_value('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_TIMEOUT = int(_env_value('EMAIL_TIMEOUT', default='10'))
SMS_ENABLED = _env_bool('SMS_ENABLED', default=False)
SMS_DEFAULT_COUNTRY_CODE = _env_value('SMS_DEFAULT_COUNTRY_CODE', default='+91')
PUBLIC_BASE_URL = _normalize_origin(
    _env_value('PUBLIC_BASE_URL', 'APP_URL', 'PUBLIC_URL', 'RENDER_EXTERNAL_URL', 'RAILWAY_PUBLIC_DOMAIN')
) or 'http://localhost:8000'
TWILIO_ACCOUNT_SID = _env_value('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = _env_value('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = _env_value('TWILIO_PHONE_NUMBER')
TWILIO_MESSAGING_SERVICE_SID = _env_value('TWILIO_MESSAGING_SERVICE_SID')
SMS_PROVIDER = _env_value(
    'SMS_PROVIDER',
    default='TWILIO' if (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and (TWILIO_PHONE_NUMBER or TWILIO_MESSAGING_SERVICE_SID))
    else 'MSG91' if _env_value('MSG91_AUTH_KEY')
    else '',
)
MSG91_AUTH_KEY = _env_value('MSG91_AUTH_KEY')
MSG91_SMS_FLOW_ID = _env_value('MSG91_SMS_FLOW_ID')
MSG91_OTP_FLOW_ID = _env_value('MSG91_OTP_FLOW_ID', default=MSG91_SMS_FLOW_ID)
MSG91_SMS_SENDER_ID = _env_value('MSG91_SMS_SENDER_ID')

# OTP verification settings
OTP_EXPIRY_MINUTES = int(_env_value('OTP_EXPIRY_MINUTES', default='10'))
OTP_MAX_ATTEMPTS = int(_env_value('OTP_MAX_ATTEMPTS', default='5'))
OTP_RESEND_COOLDOWN_SECONDS = int(_env_value('OTP_RESEND_COOLDOWN_SECONDS', default='60'))
# ─── Default PK ───────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
SESSION_COOKIE_AGE = int(_env_value('SESSION_COOKIE_AGE', default='3600'))  # 1 hour
SESSION_INACTIVITY_TIMEOUT = int(
    _env_value('SESSION_INACTIVITY_TIMEOUT', default=str(SESSION_COOKIE_AGE))
)
SESSION_SAVE_EVERY_REQUEST = True

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

if 'test' in sys.argv:
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
