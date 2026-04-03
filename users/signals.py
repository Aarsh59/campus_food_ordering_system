from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import get_connection, send_mail
from django.conf import settings
import random
import string
from .models import StaffApplication, User, VendorProfile


def generate_password(length=10):
    characters = string.ascii_letters + string.digits + '!@#$%'
    return ''.join(random.choices(characters, k=length))


def _safe_send_email(subject, message, recipient_email):
    """
    Best-effort email sender for approval/rejection signals.
    Network or SMTP issues should not block the admin action itself.
    """
    if not recipient_email:
        return

    try:
        connection = get_connection(
            fail_silently=True,
            timeout=getattr(settings, 'EMAIL_TIMEOUT', 10),
        )
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=True,
            connection=connection,
        )
    except Exception:
        pass


@receiver(post_save, sender=StaffApplication)
def handle_application_approval(sender, instance, created, **kwargs):
    print(f"🔔 SIGNAL FIRED - status: {instance.status}, created: {created}")

    # skip brand new applications
    if created:
        print("⏭️ New application — skipping")
        return

    # ── Approved ──────────────────────────────────────────────────────────────
    if instance.status == 'APPROVED':

        # dont create duplicate accounts
        if User.objects.filter(email=instance.email).exists():
            print("⚠️ User already exists — skipping account creation")
            return

        # generate credentials
        username = instance.email.split('@')[0]
        password = generate_password()

        # create user account
        created_user = User.objects.create_user(
            username   = username,
            email      = instance.email,
            password   = password,
            phone      = instance.phone,
            role       = instance.role_applied,
            first_name = instance.full_name.split()[0],
            last_name  = ' '.join(instance.full_name.split()[1:]),
        )

        # Create vendor profile on approval.
        # This enables the vendor module (location + menu + tickets).
        if instance.role_applied == 'VENDOR':
            VendorProfile.objects.create(
                user=created_user,
                outlet_name=instance.outlet_name,
                google_maps_location=instance.outlet_location,
                cuisine_type=instance.cuisine_type,
                operating_hours=instance.operating_hours,
            )

        # send approval email with credentials
        _safe_send_email(
            subject='Your Campus Food Account is Approved! 🎉',
            message=f'''Hi {instance.full_name},

Great news! Your application has been approved.

Here are your login credentials:

    Username : {username}
    Password : {password}

Login at: http://localhost:8000/login/

Please change your password after your first login for security.

Regards,
Campus Food Team''',
            recipient_email=instance.email,
        )

        print(f"✅ Account created for {instance.full_name} ({instance.role_applied})")
        print(f"   Username : {username}")
        print(f"   Password : {password}")

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

        print(f"❌ Rejection email sent to {instance.full_name}")

    # ── Pending ───────────────────────────────────────────────────────────────
    else:
        print(f"⏳ Status is PENDING — no action taken")
