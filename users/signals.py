from django.db.models.signals import post_save
from django.dispatch import receiver
import logging
import random
import string
from .models import Notification, StaffApplication, User, VendorProfile
from .username_validation import sanitize_username_seed
from .email_utils import send_app_email
from .link_utils import build_login_url, build_password_reset_url
from .sms_utils import send_app_sms

logger = logging.getLogger(__name__)


def generate_password(length=10):
    characters = string.ascii_letters + string.digits + '!@#$%'
    return ''.join(random.choices(characters, k=length))


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
    return send_app_email(subject=subject, message=message, recipient_email=recipient_email)


def _safe_send_sms(message, recipient_phone):
    """
    Best-effort SMS sender for approval/rejection signals.
    Returns whether the SMS was accepted by the backend.
    """
    return send_app_sms(message=message, recipient_phone=recipient_phone)


def _create_admin_application_notifications(application):
    admin_users = User.objects.filter(is_staff=True, is_active=True)
    if not admin_users.exists():
        return

    role_label = application.get_role_applied_display()
    message = (
        f"New {role_label} application from {application.full_name} "
        f"({application.email}) is pending review."
    )
    notifications = [
        Notification(
            recipient=admin_user,
            notification_type=Notification.NotificationType.STAFF_APPLICATION,
            message=message,
            application=application,
        )
        for admin_user in admin_users
    ]
    Notification.objects.bulk_create(notifications)


def _email_admins_about_application(application):
    admin_users = User.objects.filter(
        is_staff=True,
        is_active=True,
    ).exclude(email='')

    if not admin_users.exists():
        return

    role_label = application.get_role_applied_display()
    subject = f'New {role_label} application pending review'
    message = f'''A new {role_label} application has been submitted and is pending review.

Applicant: {application.full_name}
Email: {application.email}
Phone: {application.phone}
Applied role: {role_label}
Submitted at: {application.applied_at:%Y-%m-%d %H:%M:%S %Z}

Please review it in the Django admin Staff Applications page.
'''

    for admin_user in admin_users:
        _safe_send_email(
            subject=subject,
            message=message,
            recipient_email=admin_user.email,
        )
        _safe_send_sms(
            message=message,
            recipient_phone=admin_user.phone,
        )


@receiver(post_save, sender=StaffApplication)
def handle_application_approval(sender, instance, created, **kwargs):
    if created:
        if instance.status == StaffApplication.Status.PENDING:
            _create_admin_application_notifications(instance)
            _email_admins_about_application(instance)
        return

    # ── Approved ──────────────────────────────────────────────────────────────
    if instance.status == StaffApplication.Status.APPROVED:
        existing_user = User.objects.filter(email=instance.email).first()
        login_url = build_login_url()
        reset_url = build_password_reset_url()

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
            _safe_send_sms(
                message=(
                    f'Campus Food: your application has been approved. '
                    f'Username: {existing_user.username}. '
                    'Use the login page or your active session to continue.'
                ),
                recipient_phone=instance.phone,
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
        _safe_send_sms(
            message=(
                f'Campus Food: your application has been approved. '
                f'Username: {username}. Password: {password}. '
                'Please change your password after first login.'
            ),
            recipient_phone=instance.phone,
        )

        logger.info('Account created for %s (%s)', instance.full_name, instance.role_applied)

    # ── Rejected ──────────────────────────────────────────────────────────────
    elif instance.status == StaffApplication.Status.REJECTED:

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
        _safe_send_sms(
            message=(
                f'Campus Food: your {instance.get_role_applied_display()} application was not approved. '
                f'Reason: {instance.admin_notes if instance.admin_notes else "Not specified"}. '
                'Please contact the campus admin if you have questions.'
            ),
            recipient_phone=instance.phone,
        )
