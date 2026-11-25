"""Verify a Google Identity Services ID token (the `credential` from the Google button).

Uses Google's tokeninfo endpoint, which checks the signature and expiry on Google's
side, so no extra Python packages are needed. We then check that the token was issued
for *our* client ID, by Google, for a verified email.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleTokenError(Exception):
    """The credential is not a valid Google sign-in for this site."""


class GoogleUnavailable(Exception):
    """Google could not be reached."""


def verify_credential(credential):
    """Return the token's claims (sub, email, name, ...) or raise GoogleTokenError."""
    url = f"{TOKENINFO_URL}?{urllib.parse.urlencode({'id_token': credential})}"
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            claims = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:  # 400 = invalid or expired token
        raise GoogleTokenError("invalid token") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise GoogleUnavailable(str(exc)) from exc

    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise GoogleTokenError("token was issued for another app")
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleTokenError("unexpected issuer")
    if str(claims.get("email_verified")).lower() != "true":
        raise GoogleTokenError("email not verified by Google")
    if int(claims.get("exp", 0)) < time.time():
        raise GoogleTokenError("token expired")
    if not claims.get("sub") or not claims.get("email"):
        raise GoogleTokenError("token is missing the account id or email")
    return claims
