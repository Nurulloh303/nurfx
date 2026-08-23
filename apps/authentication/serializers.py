from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

User = get_user_model()


class GoogleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField(max_length=4096)

    def validate_id_token(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Google ID token is required.")
        return value


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "avatar_url",
            "tokens_balance",
            "created_at",
            "last_login_at",
        )
        read_only_fields = fields


class TokenBalanceSerializer(serializers.Serializer):
    tokens_balance = serializers.IntegerField(read_only=True)
    analysis_cost = serializers.IntegerField(read_only=True)
    available_analyses = serializers.IntegerField(read_only=True)


@transaction.atomic
def get_or_create_google_user(google_claims: dict) -> tuple[User, bool]:
    """Find or create a user from verified Google claims. Credit welcome bonus once."""
    from django.conf import settings

    google_id = google_claims["sub"]
    email = google_claims.get("email", "").lower()
    full_name = google_claims.get("name", "")
    avatar_url = google_claims.get("picture", "")

    user = User.objects.filter(google_id=google_id).first()
    created = False

    if user is None:
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create(
                email=email,
                google_id=google_id,
                full_name=full_name,
                avatar_url=avatar_url,
            )
            created = True
        else:
            user.google_id = google_id
            user.full_name = full_name or user.full_name
            user.avatar_url = avatar_url or user.avatar_url
            user.save(update_fields=["google_id", "full_name", "avatar_url", "updated_at"])

    if created and not user.welcome_bonus_claimed:
        user.tokens_balance += settings.NURFX_WELCOME_TOKENS
        user.welcome_bonus_claimed = True
        user.save(update_fields=["tokens_balance", "welcome_bonus_claimed", "updated_at"])

        from apps.tokens.models import TokenTransaction

        TokenTransaction.objects.create(
            user=user,
            transaction_type=TokenTransaction.Type.WELCOME_BONUS,
            token_amount=settings.NURFX_WELCOME_TOKENS,
            description="Welcome gift — 6 free tokens (2 analyses)",
        )

    user.last_login_at = timezone.now()
    user.save(update_fields=["last_login_at", "updated_at"])

    return user, created
