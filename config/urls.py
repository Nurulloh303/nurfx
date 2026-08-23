from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django_ratelimit.decorators import ratelimit

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# Rate-limit admin login attempts by IP to slow credential-stuffing/brute-force
# against the admin panel (Django's admin has no built-in login throttling).
admin.site.login = ratelimit(key="ip", rate="10/m", method="POST", block=True)(
    admin.site.login
)

urlpatterns = [
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),
    # API Documentation (Swagger & ReDoc)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # API endpoints
    path("api/v1/auth/", include("apps.authentication.urls")),
    path("api/v1/analysis/", include("apps.analysis.urls")),
    path("api/v1/tokens/", include("apps.tokens.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
