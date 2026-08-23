from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import (
    CouponRedeemSerializer,
    SubscriptionPackageSerializer,
    TokenCouponSerializer,
    TokenTransactionSerializer,
)
from .services import (
    CouponAlreadyUsedError,
    CouponExpiredError,
    CouponNotFoundError,
    get_subscription_packages,
    redeem_coupon,
)


@method_decorator(ratelimit(key="ip", rate="30/h", method="POST", block=True), name="dispatch")
class RedeemCouponView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "coupon"
    serializer_class = CouponRedeemSerializer

    @method_decorator(ratelimit(key="user", rate="10/m", method="POST", block=True))
    def post(self, request):
        serializer = CouponRedeemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            coupon = redeem_coupon(request.user, serializer.validated_data["code"])
        except CouponNotFoundError as exc:
            return Response({"success": False, "error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CouponAlreadyUsedError as exc:
            return Response({"success": False, "error": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CouponExpiredError as exc:
            return Response({"success": False, "error": str(exc)}, status=status.HTTP_410_GONE)

        request.user.refresh_from_db()
        return Response(
            {
                "success": True,
                "message": f"Successfully redeemed {coupon.token_amount} tokens.",
                "coupon": TokenCouponSerializer(coupon).data,
                "tokens_balance": request.user.tokens_balance,
            }
        )


class SubscriptionPackagesView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SubscriptionPackageSerializer

    def get(self, request):
        packages = get_subscription_packages()
        result = []
        for name, pkg in packages.items():
            result.append(
                {
                    "name": name,
                    "tokens": pkg["tokens"],
                    "price_uzs": pkg["price_uzs"],
                    "price_per_token": pkg["price_per_token"],
                    "analyses": pkg["tokens"] // 3,
                    "is_recommended": name == "PRO",
                }
            )
        serializer = SubscriptionPackageSerializer(result, many=True)
        from django.conf import settings
        return Response(
            {
                "success": True,
                "packages": serializer.data,
                "payment_info": {
                    "card_number": settings.NURFX_PAYMENT_CARD_NUMBER,
                    "card_holder": settings.NURFX_PAYMENT_CARD_HOLDER,
                    "telegram_admin": f"@{settings.NURFX_ADMIN_TELEGRAM_USERNAME}",
                    "telegram_admin_url": f"https://t.me/{settings.NURFX_ADMIN_TELEGRAM_USERNAME}",
                },
            }
        )


class TransactionHistoryView(APIView):
    serializer_class = TokenTransactionSerializer

    def get(self, request):
        from .models import TokenTransaction

        transactions = TokenTransaction.objects.filter(user=request.user)[:50]
        return Response(
            {
                "success": True,
                "transactions": TokenTransactionSerializer(transactions, many=True).data,
            }
        )
