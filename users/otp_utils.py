import base64
import logging
import random
import re
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from .email_utils import send_app_email
from .models import ContactOTP

logger = logging.getLogger(__name__)

OTP_DIGITS = 6
PHONE_RE = re.compile(r'^\d{10}$')


def normalize_email(email: str) -> str:
    return (email or '').strip().lower()


def normalize_phone(phone: str) -> str:
    return re.sub(r'\D', '', phone or '')


def is_valid_phone(phone: str) -> bool:
    return bool(PHONE_RE.match(normalize_phone(phone)))


def is_allowed_email_domain(email: str) -> bool:
    domain = getattr(settings, 'ALLOWED_EMAIL_DOMAIN', '@iitk.ac.in')
    return normalize_email(email).endswith(domain)


def generate_otp() -> str:
    return ''.join(str(random.SystemRandom().randint(0, 9)) for _ in range(OTP_DIGITS))


def issue_otp(purpose: str, channel: str, target: str) -> tuple[ContactOTP, str]:
    target = normalize_email(target) if channel == ContactOTP.Channel.EMAIL else normalize_phone(target)
    code = generate_otp()
    ContactOTP.objects.filter(
        purpose=purpose,
        channel=channel,
        target=target,
        verified_at__isnull=True,
    ).delete()
    otp = ContactOTP.objects.create(
        purpose=purpose,
        channel=channel,
        target=target,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=getattr(settings, 'OTP_EXPIRY_MINUTES', 10)),
    )
    return otp, code


def verify_otp(purpose: str, channel: str, target: str, code: str, *, consume: bool = True) -> bool:
    target = normalize_email(target) if channel == ContactOTP.Channel.EMAIL else normalize_phone(target)
    code = (code or '').strip()
    if not re.fullmatch(r'\d{6}', code):
        return False

    otp = (
        ContactOTP.objects
        .filter(purpose=purpose, channel=channel, target=target, verified_at__isnull=True)
        .order_by('-created_at')
        .first()
    )
    if not otp or otp.is_expired():
        return False

    max_attempts = getattr(settings, 'OTP_MAX_ATTEMPTS', 5)
    if otp.attempts >= max_attempts:
        return False

    if check_password(code, otp.code_hash):
        if consume:
            otp.attempts += 1
            otp.verified_at = timezone.now()
            otp.save(update_fields=['attempts', 'verified_at'])
        return True

    otp.attempts += 1
    otp.save(update_fields=['attempts'])
    return False


def send_email_otp(email: str, code: str) -> bool:
    return send_app_email(
        subject='Your IITK Food verification code',
        message=(
            f'Your IITK Food verification code is {code}.\n\n'
            f'This code expires in {getattr(settings, "OTP_EXPIRY_MINUTES", 10)} minutes. '
            'If you did not request this, you can ignore this email.'
        ),
        recipient_email=normalize_email(email),
    )


def _phone_to_e164(phone: str) -> str:
    phone = normalize_phone(phone)
    country_code = getattr(settings, 'OTP_PHONE_COUNTRY_CODE', '+91')
    return f'{country_code}{phone}'


def send_phone_otp(phone: str, code: str) -> bool:
    backend = getattr(settings, 'OTP_SMS_BACKEND', 'console')
    if backend == 'console':
        logger.warning('Phone OTP for %s is %s', normalize_phone(phone), code)
        return True

    if backend != 'twilio':
        logger.error('Unsupported OTP_SMS_BACKEND: %s', backend)
        return False

    account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    from_number = getattr(settings, 'TWILIO_FROM_NUMBER', '')
    if not all([account_sid, auth_token, from_number]):
        logger.error('Twilio SMS OTP is not configured.')
        return False

    url = f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json'
    payload = urllib.parse.urlencode({
        'From': from_number,
        'To': _phone_to_e164(phone),
        'Body': f'Your IITK Food verification code is {code}. It expires in {getattr(settings, "OTP_EXPIRY_MINUTES", 10)} minutes.',
    }).encode('utf-8')
    token = base64.b64encode(f'{account_sid}:{auth_token}'.encode('utf-8')).decode('ascii')
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'campus-food-ordering-system/1.0',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(request, timeout=getattr(settings, 'EMAIL_TIMEOUT', 10)) as response:
            if response.status in (200, 201):
                return True
            logger.error('Twilio returned status %s: %s', response.status, response.read().decode('utf-8', errors='replace'))
    except Exception:
        logger.exception('Failed to send phone OTP through Twilio.')
    return False


def send_otp(purpose: str, channel: str, target: str) -> bool:
    _, code = issue_otp(purpose, channel, target)
    if channel == ContactOTP.Channel.EMAIL:
        return send_email_otp(target, code)
    return send_phone_otp(target, code)
