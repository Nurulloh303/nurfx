import logging

from django.conf import settings
from google.auth.transport import requests
from google.oauth2 import id_token

logger = logging.getLogger(__name__)


class GoogleOAuthError(Exception):
    pass


def verify_google_id_token(token: str) -> dict:
    """
    Verify a Google OAuth 2.0 ID token and return decoded claims.
    Raises GoogleOAuthError on invalid/expired tokens.
    """
    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            settings.GOOGLE_OAUTH_CLIENT_ID,
        )
        if idinfo["iss"] not in ("accounts.google.com", "https://accounts.google.com"):
            raise GoogleOAuthError("Invalid token issuer")
        return idinfo
    except ValueError as exc:
        logger.warning("Google token verification failed: %s", exc)
        raise GoogleOAuthError("Invalid or expired Google token") from exc
