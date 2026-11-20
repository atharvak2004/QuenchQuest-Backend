from .tokens import access_token


def generate_token(user):
    """Access token for a volunteer (kept for existing callers)."""
    return access_token(user)
