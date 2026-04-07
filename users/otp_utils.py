import random
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from .email_utils import send_app_email
from .models import ContactOTP

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


def send_otp(purpose: str, channel: str, target: str) -> bool:
    _, code = issue_otp(purpose, channel, target)
    return send_email_otp(target, code)
