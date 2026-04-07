import re


USERNAME_ALLOWED_DESCRIPTION = 'letters, numbers, and @/./+/-/_ only'
USERNAME_ALLOWED_PATTERN = re.compile(r'^[A-Za-z0-9@.+_-]+\Z')
USERNAME_DISALLOWED_PATTERN = re.compile(r'[^A-Za-z0-9@.+_-]+')


def is_valid_username(username: str) -> bool:
    return bool(username and USERNAME_ALLOWED_PATTERN.fullmatch(username))


def sanitize_username_seed(value: str, fallback: str = 'user', max_length: int = 140) -> str:
    username = USERNAME_DISALLOWED_PATTERN.sub('', value or '')[:max_length]
    return username or fallback
