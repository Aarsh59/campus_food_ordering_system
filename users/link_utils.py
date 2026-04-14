from django.conf import settings


def build_public_base_url() -> str:
    return (getattr(settings, 'PUBLIC_BASE_URL', '') or 'http://localhost:8000').rstrip('/')


def build_public_url(path: str = '/') -> str:
    normalized_path = path or '/'
    if not normalized_path.startswith('/'):
        normalized_path = f'/{normalized_path}'
    return f'{build_public_base_url()}{normalized_path}'


def build_portal_entry_url() -> str:
    return build_public_url('/')


def build_login_url() -> str:
    return build_public_url('/login/')


def build_password_reset_url() -> str:
    return build_public_url('/password-reset/')
