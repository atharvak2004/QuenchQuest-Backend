"""Signed, expiring preview links so drafts can be viewed on the website."""
from django.core import signing

PREVIEW_SALT = "content-preview"
PREVIEW_MAX_AGE = 60 * 60  # 1 hour


def make_preview_token(content_type, pk):
    return signing.dumps({"t": content_type, "id": pk}, salt=PREVIEW_SALT)


def read_preview_token(token):
    """Return {"t": type, "id": pk} or None if the token is bad or expired."""
    try:
        return signing.loads(token, salt=PREVIEW_SALT, max_age=PREVIEW_MAX_AGE)
    except signing.BadSignature:
        return None
