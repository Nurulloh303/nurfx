from django.conf import settings
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .google_oauth import GoogleOAuthError, verify_google_id_token
from .serializers import (
    GoogleAuthSerializer,
    TokenBalanceSerializer,
    UserProfileSerializer,
    get_or_create_google_user,
)


def _set_jwt_cookies(response: Response, refresh: RefreshToken) -> Response:
    """Attach secure HTTP-only JWT cookies alongside JSON body tokens."""
    access = refresh.access_token
    response.set_cookie(
        key=settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token"),
        value=str(access),
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        secure=settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", True),
        httponly=settings.SIMPLE_JWT.get("AUTH_COOKIE_HTTP_ONLY", True),
        samesite=settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax"),
    )
    response.set_cookie(
        key="refresh_token",
        value=str(refresh),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        secure=settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", True),
        httponly=True,
        samesite="Lax",
    )
    return response


@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True), name="dispatch")
class GoogleAuthView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"
    serializer_class = GoogleAuthSerializer

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            claims = verify_google_id_token(serializer.validated_data["id_token"])
        except GoogleOAuthError as exc:
            return Response({"success": False, "error": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        user, created = get_or_create_google_user(claims)
        refresh = RefreshToken.for_user(user)

        response = Response(
            {
                "success": True,
                "created": created,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserProfileSerializer(user).data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
        return _set_jwt_cookies(response, refresh)


from drf_spectacular.utils import extend_schema


class LogoutView(APIView):
    @extend_schema(
        request={"application/json": {"type": "object", "properties": {"refresh": {"type": "string"}}}},
        responses={200: {"type": "object", "properties": {"success": {"type": "boolean"}, "message": {"type": "string"}}}},
    )
    def post(self, request):
        refresh_token = request.data.get("refresh") or request.COOKIES.get("refresh_token")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass
        response = Response({"success": True, "message": "Logged out successfully."})
        response.delete_cookie(settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token"))
        response.delete_cookie("refresh_token")
        return response


class UserProfileView(APIView):
    serializer_class = UserProfileSerializer

    def get(self, request):
        return Response({"success": True, "user": UserProfileSerializer(request.user).data})


class TokenBalanceView(APIView):
    serializer_class = TokenBalanceSerializer

    def get(self, request):
        cost = settings.NURFX_ANALYSIS_TOKEN_COST
        balance = request.user.tokens_balance
        data = {
            "tokens_balance": balance,
            "analysis_cost": cost,
            "available_analyses": balance // cost,
        }
        return Response({"success": True, **TokenBalanceSerializer(data).data})


class SecureTokenRefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and "access" in response.data:
            response.set_cookie(
                key=settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token"),
                value=response.data["access"],
                max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
                secure=settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", True),
                httponly=True,
                samesite="Lax",
            )
        return response
