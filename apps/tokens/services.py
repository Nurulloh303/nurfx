import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import TokenCoupon, TokenTransaction, generate_coupon_code

User = get_user_model()
logger = logging.getLogger(__name__)

COUPON_VALIDITY_DAYS = 30


class InsufficientTokensError(Exception):
    pass


class CouponAlreadyUsedError(Exception):
    pass


class CouponNotFoundError(Exception):
    pass


class CouponExpiredError(Exception):
    pass


@transaction.atomic
def redeem_coupon(user: User, code: str) -> TokenCoupon:
    """
    Redeem a single-use coupon. Uses select_for_update to prevent race conditions.
    """
    normalized_code = code.strip().upper()

    try:
        coupon = TokenCoupon.objects.select_for_update().get(code=normalized_code)
    except TokenCoupon.DoesNotExist as exc:
        raise CouponNotFoundError(f"Coupon '{normalized_code}' not found.") from exc

    if coupon.is_used:
        raise CouponAlreadyUsedError(f"Coupon '{normalized_code}' has already been redeemed.")

    if coupon.is_expired:
        raise CouponExpiredError(f"Coupon '{normalized_code}' has expired.")

    user_locked = User.objects.select_for_update().get(pk=user.pk)
    user_locked.tokens_balance += coupon.token_amount
    user_locked.save(update_fields=["tokens_balance", "updated_at"])

    coupon.is_used = True
    coupon.used_by = user_locked
    coupon.used_at = timezone.now()
    coupon.save(update_fields=["is_used", "used_by", "used_at"])

    TokenTransaction.objects.create(
        user=user_locked,
        transaction_type=TokenTransaction.Type.COUPON_REDEMPTION,
        token_amount=coupon.token_amount,
        description=f"Redeemed coupon {coupon.code}",
        coupon=coupon,
    )

    logger.info("User %s redeemed coupon %s for %d tokens", user_locked.email, coupon.code, coupon.token_amount)
    return coupon


@transaction.atomic
def deduct_analysis_tokens(user: User, analysis_id: str) -> int:
    """Deduct tokens for an analysis. Returns remaining balance."""
    from django.conf import settings

    cost = settings.NURFX_ANALYSIS_TOKEN_COST
    user_locked = User.objects.select_for_update().get(pk=user.pk)

    if user_locked.tokens_balance < cost:
        raise InsufficientTokensError(
            f"Insufficient tokens. Required: {cost}, Available: {user_locked.tokens_balance}"
        )

    user_locked.tokens_balance -= cost
    user_locked.save(update_fields=["tokens_balance", "updated_at"])

    TokenTransaction.objects.create(
        user=user_locked,
        transaction_type=TokenTransaction.Type.ANALYSIS_DEDUCTION,
        token_amount=-cost,
        description=f"Analysis {analysis_id}",
    )

    return user_locked.tokens_balance


@transaction.atomic
def create_coupon(token_amount: int, custom_price_uzs: int) -> TokenCoupon:
    """Generate a unique single-use coupon code."""
    if token_amount <= 0:
        raise ValidationError("token_amount must be positive.")
    if custom_price_uzs <= 0:
        raise ValidationError("custom_price_uzs must be positive.")

    for _ in range(10):
        code = generate_coupon_code()
        if not TokenCoupon.objects.filter(code=code).exists():
            return TokenCoupon.objects.create(
                code=code,
                token_amount=token_amount,
                custom_price_uzs=custom_price_uzs,
                expires_at=timezone.now() + timedelta(days=COUPON_VALIDITY_DAYS),
            )

    raise ValidationError("Failed to generate unique coupon code after 10 attempts.")


def get_subscription_packages() -> dict:
    from django.conf import settings
    return settings.NURFX_SUBSCRIPTION_PACKAGES
