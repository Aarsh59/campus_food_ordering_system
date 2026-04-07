import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    """
    Django email backend that uses Resend's HTTPS API instead of SMTP.
    Useful on hosts where outbound SMTP is blocked.
    """

    api_url = 'https://api.resend.com/emails'

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = getattr(settings, 'RESEND_API_KEY', '')
        if not api_key:
            logger.error('RESEND_API_KEY is not configured.')
            if self.fail_silently:
                return 0
            raise ValueError('RESEND_API_KEY is not configured.')

        sent_count = 0
        for message in email_messages:
            try:
                self._send_message(api_key, message)
            except Exception:
                logger.exception('Failed to send email through Resend to %s', message.to)
                if not self.fail_silently:
                    raise
            else:
                sent_count += 1
        return sent_count

    def _send_message(self, api_key, message):
        payload = {
            'from': message.from_email or settings.DEFAULT_FROM_EMAIL,
            'to': message.to,
            'subject': message.subject,
            'text': message.body,
        }
        if message.cc:
            payload['cc'] = message.cc
        if message.bcc:
            payload['bcc'] = message.bcc
        if message.reply_to:
            payload['reply_to'] = message.reply_to

        html_body = self._get_html_body(message)
        if html_body:
            payload['html'] = html_body

        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'campus-food-ordering-system/1.0',
            },
            method='POST',
        )

        try:
            with urllib.request.urlopen(request, timeout=getattr(settings, 'EMAIL_TIMEOUT', 10)) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f'Resend returned HTTP {response.status}')
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'Resend returned HTTP {exc.code}: {detail}') from exc

    def _get_html_body(self, message):
        alternatives = getattr(message, 'alternatives', None) or []
        for content, mimetype in alternatives:
            if mimetype == 'text/html':
                return content
        return ''
