import logging

from django.conf import settings
from django.core.mail import get_connection, send_mail

logger = logging.getLogger(__name__)


def send_app_email(subject: str, message: str, recipient_email: str) -> bool:
    """
    Send a plain-text app email through the configured Django email backend.
    """
    if not recipient_email:
        logger.warning('Skipping email because recipient address is empty.')
        return False

    uses_smtp = settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend'
    if uses_smtp and (not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD):
        logger.error('Email is not configured. Set EMAIL_USER/EMAIL_PASSWORD or EMAIL_HOST_USER/EMAIL_HOST_PASSWORD.')
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
    except Exception:
        logger.exception('Failed to send email to %s', recipient_email)
        return False

    if sent_count:
        logger.info('Email sent to %s', recipient_email)
        return True

    logger.warning('Email backend returned 0 recipients for %s', recipient_email)
    return False
