from django.http import JsonResponse
from django_ratelimit.exceptions import Ratelimited


def ratelimit_handler(request, exception=None):
    return JsonResponse(
        {"success": False, "error": "Rate limit exceeded. Please try again later."},
        status=429,
    )
