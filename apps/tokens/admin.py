from django.contrib import admin

from .models import TokenCoupon, TokenTransaction


@admin.register(TokenCoupon)
class TokenCouponAdmin(admin.ModelAdmin):
    list_display = ("code", "token_amount", "custom_price_uzs", "is_used", "used_by", "created_at", "used_at", "expires_at")
    list_filter = ("is_used",)
    search_fields = ("code", "used_by__email")
    readonly_fields = ("id", "code", "created_at", "used_at", "used_by")
    ordering = ("-created_at",)


@admin.register(TokenTransaction)
class TokenTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "transaction_type", "token_amount", "description", "created_at")
    list_filter = ("transaction_type",)
    search_fields = ("user__email", "description")
    readonly_fields = ("id", "created_at")
    ordering = ("-created_at",)
