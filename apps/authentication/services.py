import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@transaction.atomic
def get_or_create_telegram_user(telegram_id: int, full_name: str = ""):
    """
    Find or create the account behind a Telegram user, crediting the welcome
    bonus once — the same rule the Google sign-in path applies.

    The address is a synthetic, non-routable placeholder. It is deliberately
    not something the user can choose: letting someone type an arbitrary email
    here would let them claim an address they do not own, and the Google
    sign-in path attaches to an existing account by email. Linking a Telegram
    account to a real one needs a one-time code issued to an already
    authenticated web session — add that with the frontend.
    """
    User = get_user_model()

    user = User.objects.filter(telegram_id=telegram_id).first()
    created = False

    if user is None:
        user = User.objects.create_user(
            email=f"tg-{telegram_id}@telegram.local",
            telegram_id=telegram_id,
            full_name=full_name,
        )
        created = True

    if created and not user.welcome_bonus_claimed:
        user.tokens_balance += settings.NURFX_WELCOME_TOKENS
        user.welcome_bonus_claimed = True
        user.save(update_fields=["tokens_balance", "welcome_bonus_claimed", "updated_at"])

        from apps.tokens.models import TokenTransaction

        TokenTransaction.objects.create(
            user=user,
            transaction_type=TokenTransaction.Type.WELCOME_BONUS,
            token_amount=settings.NURFX_WELCOME_TOKENS,
            description=f"Welcome gift — {settings.NURFX_WELCOME_TOKENS} tokens (Telegram)",
        )
        logger.info("Created Telegram user %s with welcome bonus", telegram_id)

    user.last_login_at = timezone.now()
    user.save(update_fields=["last_login_at", "updated_at"])

    return user, created
