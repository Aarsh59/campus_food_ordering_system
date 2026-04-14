import base64
import json
import logging
import re
from urllib import error, parse, request

from django.conf import settings

from .link_utils import build_portal_entry_url

logger = logging.getLogger(__name__)

INTERNATIONAL_PHONE_RE = re.compile(r'^\d{10,15}$')


def normalize_phone_for_sms(phone: str, *, include_plus: bool = False) -> str:
    raw_phone = (phone or '').strip()
    digits = re.sub(r'\D', '', raw_phone)
    if not digits:
        return ''

    country_code = (getattr(settings, 'SMS_DEFAULT_COUNTRY_CODE', '+91') or '+91').strip()
    country_code_digits = re.sub(r'\D', '', country_code)

    if country_code_digits == '91' and len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]

    if len(digits) == 10:
        digits = f'{country_code_digits}{digits}'

    return f'+{digits}' if include_plus else digits


def _sms_provider() -> str:
    return (getattr(settings, 'SMS_PROVIDER', '') or '').strip().upper()


def _append_portal_link(message: str) -> str:
    message = (message or '').strip()
    portal_url = build_portal_entry_url()
    if portal_url in message:
        return message
    if message:
        return f'{message}\nOpen Campus Food: {portal_url}'
    return f'Open Campus Food: {portal_url}'


def _sms_is_configured() -> bool:
    if not getattr(settings, 'SMS_ENABLED', False):
        return False

    provider = _sms_provider()
    if provider == 'TWILIO':
        if not getattr(settings, 'TWILIO_ACCOUNT_SID', ''):
            logger.error('SMS is enabled but TWILIO_ACCOUNT_SID is missing.')
            return False
        if not getattr(settings, 'TWILIO_AUTH_TOKEN', ''):
            logger.error('SMS is enabled but TWILIO_AUTH_TOKEN is missing.')
            return False
        if not (
            getattr(settings, 'TWILIO_PHONE_NUMBER', '')
            or getattr(settings, 'TWILIO_MESSAGING_SERVICE_SID', '')
        ):
            logger.error(
                'SMS is enabled but neither TWILIO_PHONE_NUMBER nor '
                'TWILIO_MESSAGING_SERVICE_SID is configured.'
            )
            return False
        return True

    if provider == 'MSG91':
        if not getattr(settings, 'MSG91_AUTH_KEY', ''):
            logger.error('SMS is enabled but MSG91_AUTH_KEY is missing.')
            return False
        return True

    logger.error('SMS is enabled but SMS_PROVIDER is not configured to TWILIO or MSG91.')
    return False


def _send_msg91_flow(recipient_phone: str, flow_id: str, variables: dict[str, str]) -> bool:
    if not flow_id:
        logger.error('MSG91 flow id is missing.')
        return False

    payload = {
        'flow_id': flow_id,
        'recipients': [
            {
                'mobiles': recipient_phone,
                **variables,
            }
        ],
    }
    sender_id = getattr(settings, 'MSG91_SMS_SENDER_ID', '')
    if sender_id:
        payload['sender'] = sender_id

    req = request.Request(
        url='https://api.msg91.com/api/v5/flow/',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'accept': 'application/json',
            'authkey': settings.MSG91_AUTH_KEY,
            'content-type': 'application/json',
        },
        method='POST',
    )

    try:
        with request.urlopen(req, timeout=10) as response:
            status_code = getattr(response, 'status', 200)
            body = response.read().decode('utf-8', errors='replace')
    except error.HTTPError as exc:
        logger.exception('MSG91 rejected SMS for %s with status %s', recipient_phone, exc.code)
        return False
    except Exception:
        logger.exception('Unexpected MSG91 SMS failure for %s', recipient_phone)
        return False

    if 200 <= status_code < 300:
        logger.info('MSG91 SMS accepted for %s: %s', recipient_phone, body)
        return True

    logger.error('MSG91 SMS failed for %s with status %s: %s', recipient_phone, status_code, body)
    return False


def _send_twilio_sms(recipient_phone: str, message: str) -> bool:
    account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    phone_number = getattr(settings, 'TWILIO_PHONE_NUMBER', '')
    messaging_service_sid = getattr(settings, 'TWILIO_MESSAGING_SERVICE_SID', '')

    payload = {
        'To': recipient_phone,
        'Body': message,
    }
    if messaging_service_sid:
        payload['MessagingServiceSid'] = messaging_service_sid
    elif phone_number:
        payload['From'] = phone_number

    credentials = f'{account_sid}:{auth_token}'.encode('utf-8')
    auth_header = base64.b64encode(credentials).decode('ascii')
    req = request.Request(
        url=f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json',
        data=parse.urlencode(payload).encode('utf-8'),
        headers={
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        method='POST',
    )

    try:
        with request.urlopen(req, timeout=10) as response:
            status_code = getattr(response, 'status', 200)
            body = response.read().decode('utf-8', errors='replace')
    except error.HTTPError as exc:
        error_body = exc.read().decode('utf-8', errors='replace')
        logger.exception('Twilio rejected SMS for %s with status %s: %s', recipient_phone, exc.code, error_body)
        return False
    except Exception:
        logger.exception('Unexpected Twilio SMS failure for %s', recipient_phone)
        return False

    if 200 <= status_code < 300:
        logger.info('Twilio SMS accepted for %s: %s', recipient_phone, body)
        return True

    logger.error('Twilio SMS failed for %s with status %s: %s', recipient_phone, status_code, body)
    return False


def send_app_sms(message: str, recipient_phone: str) -> bool:
    """
    Send a plain-text SMS through the configured provider.
    """
    if not recipient_phone:
        logger.warning('Skipping SMS because recipient phone is empty.')
        return False

    if not _sms_is_configured():
        return False

    provider = _sms_provider()
    normalized_digits = normalize_phone_for_sms(recipient_phone)
    if not INTERNATIONAL_PHONE_RE.fullmatch(normalized_digits):
        logger.warning('Skipping SMS because phone number is invalid: %s', recipient_phone)
        return False

    sms_message = _append_portal_link(message)
    if provider == 'TWILIO':
        return _send_twilio_sms(
            recipient_phone=normalize_phone_for_sms(recipient_phone, include_plus=True),
            message=sms_message,
        )

    return _send_msg91_flow(
        recipient_phone=normalized_digits,
        flow_id=getattr(settings, 'MSG91_SMS_FLOW_ID', ''),
        variables={'message': sms_message[:700]},
    )


def send_app_sms_otp(code: str, recipient_phone: str) -> bool:
    """
    Send OTP SMS through the configured provider.
    """
    if not recipient_phone:
        logger.warning('Skipping OTP SMS because recipient phone is empty.')
        return False

    if not _sms_is_configured():
        return False

    provider = _sms_provider()
    normalized_digits = normalize_phone_for_sms(recipient_phone)
    if not INTERNATIONAL_PHONE_RE.fullmatch(normalized_digits):
        logger.warning('Skipping OTP SMS because phone number is invalid: %s', recipient_phone)
        return False

    sms_message = _append_portal_link(
        f'Your Campus Food verification code is {code}. '
        f'This code expires in {getattr(settings, "OTP_EXPIRY_MINUTES", 10)} minutes.'
    )
    if provider == 'TWILIO':
        return _send_twilio_sms(
            recipient_phone=normalize_phone_for_sms(recipient_phone, include_plus=True),
            message=sms_message,
        )

    return _send_msg91_flow(
        recipient_phone=normalized_digits,
        flow_id=getattr(settings, 'MSG91_OTP_FLOW_ID', ''),
        variables={'otp': code, 'message': sms_message[:700]},
    )
