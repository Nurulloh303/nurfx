import secrets
import string
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def generate_coupon_code() -> str:
    """Generate a unique uppercase coupon code like NURFX-8-X92A7K4T.

    8-character random suffix (36^8 ≈ 2.8e12 combinations) instead of 4
    (36^4 ≈ 1.68e6) to make brute-forcing an active, unused coupon
    code impractical even across many accounts.
    """
    suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    return f"NURFX-{settings.NURFX_BASE_TOKEN_VALUE_UZS // 1000}-{suffix}"


class TokenCoupon(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=32, unique=True, db_index=True)
    token_amount = models.PositiveIntegerField()
    custom_price_uzs = models.PositiveIntegerField()
    is_used = models.BooleanField(default=False, db_index=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redeemed_coupons",
    )
    created_at = models.DateTimeField(default=timezone.now)
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "token_coupons"
        ordering = ["-created_at"]

    def __str__(self):
        status = "USED" if self.is_used else "ACTIVE"
        return f"{self.code} ({self.token_amount} tokens) [{status}]"

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at) and self.expires_at < timezone.now()


class TokenTransaction(models.Model):
    class Type(models.TextChoices):
        WELCOME_BONUS = "welcome_bonus", "Welcome Bonus"
        COUPON_REDEMPTION = "coupon_redemption", "Coupon Redemption"
        SUBSCRIPTION_PURCHASE = "subscription_purchase", "Subscription Purchase"
        ANALYSIS_DEDUCTION = "analysis_deduction", "Analysis Deduction"
        ADMIN_ADJUSTMENT = "admin_adjustment", "Admin Adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="token_transactions",
    )
    transaction_type = models.CharField(max_length=32, choices=Type.choices)
    token_amount = models.IntegerField(help_text="Positive for credit, negative for debit")
    description = models.CharField(max_length=512, blank=True)
    coupon = models.ForeignKey(
        TokenCoupon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    package_name = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "token_transactions"
        ordering = ["-created_at"]

    def __str__(self):
        sign = "+" if self.token_amount >= 0 else ""
        return f"{self.user.email} {sign}{self.token_amount} ({self.transaction_type})"
