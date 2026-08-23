from django.urls import path
from rest_framework_simplejwt.views import TokenVerifyView

from .views import (
    GoogleAuthView,
    LogoutView,
    SecureTokenRefreshView,
    TokenBalanceView,
    UserProfileView,
)

urlpatterns = [
    path("google/", GoogleAuthView.as_view(), name="google-auth"),
    path("refresh/", SecureTokenRefreshView.as_view(), name="token-refresh"),
    path("verify/", TokenVerifyView.as_view(), name="token-verify"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", UserProfileView.as_view(), name="user-profile"),
    path("balance/", TokenBalanceView.as_view(), name="token-balance"),
]
