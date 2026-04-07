from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from users.email_utils import send_app_email


def _mask_email(value: str) -> str:
    if not value or '@' not in value:
        return 'not set'
    name, domain = value.split('@', 1)
    if len(name) <= 2:
        masked_name = '*' * len(name)
    else:
        masked_name = f'{name[0]}***{name[-1]}'
    return f'{masked_name}@{domain}'


class Command(BaseCommand):
    help = 'Send a small test email using the configured email backend.'

    def add_arguments(self, parser):
        parser.add_argument('recipient_email', help='Email address that should receive the SMTP test message.')

    def handle(self, *args, **options):
        recipient_email = options['recipient_email']
        self.stdout.write(f'Backend: {settings.EMAIL_BACKEND}')
        self.stdout.write(f'Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}')
        self.stdout.write(f'TLS: {settings.EMAIL_USE_TLS}, SSL: {settings.EMAIL_USE_SSL}')
        self.stdout.write(f'User: {_mask_email(settings.EMAIL_HOST_USER)}')
        self.stdout.write(f'Password configured: {bool(settings.EMAIL_HOST_PASSWORD)}')
        self.stdout.write(f'Resend API key configured: {bool(getattr(settings, "RESEND_API_KEY", ""))}')
        self.stdout.write(f'From: {settings.DEFAULT_FROM_EMAIL or "not set"}')

        sent = send_app_email(
            subject='Campus Food SMTP test',
            message='If you received this, Campus Food SMTP is configured correctly.',
            recipient_email=recipient_email,
        )

        if not sent:
            raise CommandError('Test email was not sent. Check the error log above for the exact email backend failure.')

        self.stdout.write(self.style.SUCCESS(f'Test email sent to {recipient_email}.'))
