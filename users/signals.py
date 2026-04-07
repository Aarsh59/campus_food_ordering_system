from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import get_connection, send_mail
from django.conf import settings
import logging
import os
import random
import string
from .models import StaffApplication, User, VendorProfile
from .username_validation import sanitize_username_seed

logger = logging.getLogger(__name__)


def generate_password(length=10):
    characters = string.ascii_letters + string.digits + '!@#$%'
    return ''.join(random.choices(characters, k=length))


def _build_login_url() -> str:
    base_url = (
        os.getenv('APP_URL')
        or os.getenv('PUBLIC_URL')
        or os.getenv('RENDER_EXTERNAL_URL')
        or 'http://localhost:8000'
    ).rstrip('/')
    return f'{base_url}/login/'


def _build_password_reset_url() -> str:
    base_url = (
        os.getenv('APP_URL')
        or os.getenv('PUBLIC_URL')
        or os.getenv('RENDER_EXTERNAL_URL')
        or 'http://localhost:8000'
    ).rstrip('/')
    return f'{base_url}/password-reset/'


def _build_unique_username(email: str) -> str:
    base_username = sanitize_username_seed((email or '').split('@')[0])
    username = base_username
    counter = 1
    while User.objects.filter(username__iexact=username).exists():
        username = f'{base_username}{counter}'
        counter += 1
    return username


def _safe_send_email(subject, message, recipient_email):
    """
    Best-effort email sender for approval/rejection signals.
    Returns whether the email was accepted by the backend.
    """
    if not recipient_email:
        logger.warning('Skipping email because recipient address is empty.')
        return False

    try:
        connection = get_connection(
            fail_silently=False,
            timeout=getattr(settings, 'EMAIL_TIMEOUT', 10),
        )
        sent_count = send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER,
            recipient_list=[recipient_email],
            fail_silently=False,
            connection=connection,
        )
        if sent_count:
            logger.info('Approval workflow email sent to %s', recipient_email)
            return True
        logger.warning('Email backend returned 0 recipients for %s', recipient_email)
        return False
    except Exception:
        logger.exception('Failed to send email to %s', recipient_email)
        return False


@receiver(post_save, sender=StaffApplication)
def handle_application_approval(sender, instance, created, **kwargs):
    # skip brand new applications
    if created:
        return

    # ── Approved ──────────────────────────────────────────────────────────────
    if instance.status == 'APPROVED':
        existing_user = User.objects.filter(email=instance.email).first()
        login_url = _build_login_url()
        reset_url = _build_password_reset_url()

        if existing_user:
            _safe_send_email(
                subject='Your Campus Food Account is Approved! 🎉',
                message=f'''Hi {instance.full_name},

Great news! Your application has been approved.

Your account already exists with the username:

    Username : {existing_user.username}

Login at: {login_url}

If you do not know your password, reset it here:
{reset_url}

Regards,
Campus Food Team''',
                recipient_email=instance.email,
            )
            logger.info('Approval email re-sent for existing user %s', existing_user.username)
            return

        username = _build_unique_username(instance.email)
        password = generate_password()

        created_user = User.objects.create_user(
            username=username,
            email=instance.email,
            password=password,
            phone=instance.phone,
            role=instance.role_applied,
            first_name=instance.full_name.split()[0],
            last_name=' '.join(instance.full_name.split()[1:]),
        )

        if instance.role_applied == 'VENDOR':
            VendorProfile.objects.get_or_create(
                user=created_user,
                defaults={
                    'outlet_name': instance.outlet_name,
                    'google_maps_location': instance.outlet_location,
                    'cuisine_type': instance.cuisine_type,
                    'operating_hours': instance.operating_hours,
                }
            )

        _safe_send_email(
            subject='Your Campus Food Account is Approved! 🎉',
            message=f'''Hi {instance.full_name},

Great news! Your application has been approved.

Here are your login credentials:

    Username : {username}
    Password : {password}

Login at: {login_url}

Please change your password after your first login for security.
If this email arrives late and you have already changed your password, you can still sign in with your latest password.

Regards,
Campus Food Team''',
            recipient_email=instance.email,
        )

        logger.info('Account created for %s (%s)', instance.full_name, instance.role_applied)

    # ── Rejected ──────────────────────────────────────────────────────────────
    elif instance.status == 'REJECTED':

        # send rejection email
        _safe_send_email(
            subject='Update on your Campus Food Application',
            message=f'''Hi {instance.full_name},

Thank you for applying to Campus Food.

Unfortunately your application as {instance.get_role_applied_display()} 
has not been approved at this time.

Reason: {instance.admin_notes if instance.admin_notes else 'Not specified'}

If you believe this is a mistake or have questions, 
please contact the campus admin.

Regards,
Campus Food Team''',
            recipient_email=instance.email,
        )
