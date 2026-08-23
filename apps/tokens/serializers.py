from rest_framework import serializers

from .models import TokenCoupon, TokenTransaction


class CouponRedeemSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32, min_length=8)

    def validate_code(self, value):
        return value.strip().upper()


class TokenCouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = TokenCoupon
        fields = (
            "id",
            "code",
            "token_amount",
            "custom_price_uzs",
            "is_used",
            "created_at",
            "used_at",
            "expires_at",
        )
        read_only_fields = fields


class TokenTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TokenTransaction
        fields = (
            "id",
            "transaction_type",
            "token_amount",
            "description",
            "package_name",
            "created_at",
        )
        read_only_fields = fields


class SubscriptionPackageSerializer(serializers.Serializer):
    name = serializers.CharField()
    tokens = serializers.IntegerField()
    price_uzs = serializers.IntegerField()
    price_per_token = serializers.IntegerField()
    analyses = serializers.IntegerField()
    is_recommended = serializers.BooleanField(default=False)
