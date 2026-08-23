from django.conf import settings
from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    """
    Authenticate via the `Authorization: Bearer` header when present (API/mobile
    clients), otherwise fall back to the HTTP-only access_token cookie set by
    GoogleAuthView (web clients). Without this fallback, JWTAuthentication only
    reads the header, so the HTTP-only cookie is set but never actually used —
    forcing browser clients to keep the raw token in JS-reachable storage
    (e.g. localStorage) to authenticate at all, which defeats the purpose of
    issuing it as an HTTP-only cookie in the first place.
    """

    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            return super().authenticate(request)

        cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token")
        raw_token = request.COOKIES.get(cookie_name)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token


class CookieJWTScheme(SimpleJWTScheme):
    """Teach drf-spectacular that this is still bearer-token auth."""

    target_class = CookieJWTAuthentication
    name = "CookieJWTAuthentication"
