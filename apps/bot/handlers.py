import logging
import re

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from asgiref.sync import sync_to_async
from django.conf import settings

logger = logging.getLogger(__name__)

router = Router()

COUPON_PATTERN = re.compile(
    r"^/generate_coupon\s+tokens=(\d+)\s+price=(\d+)$",
    re.IGNORECASE,
)


def _is_admin(telegram_id: int) -> bool:
    return str(telegram_id) in settings.TELEGRAM_ADMIN_IDS


@sync_to_async
def _create_coupon(token_amount: int, custom_price_uzs: int):
    from apps.tokens.services import create_coupon
    return create_coupon(token_amount, custom_price_uzs)


@sync_to_async
def _redeem_coupon_for_telegram_user(telegram_id: int, code: str):
    from django.contrib.auth import get_user_model
    from apps.tokens.services import (
        CouponAlreadyUsedError,
        CouponExpiredError,
        CouponNotFoundError,
        redeem_coupon,
    )

    User = get_user_model()
    try:
        user = User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return None, "Account not linked. Sign in via NurFX.ai web app first."

    try:
        coupon = redeem_coupon(user, code)
        user.refresh_from_db()
        return coupon, user.tokens_balance
    except CouponNotFoundError as exc:
        return None, str(exc)
    except CouponAlreadyUsedError as exc:
        return None, str(exc)
    except CouponExpiredError as exc:
        return None, str(exc)


from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

SITE_BUTTON = InlineKeyboardButton(
    text="🌐 nurfxai.uz saytiga o'tish", url="https://nurfxai.uz"
)


def _admin_button(label: str) -> list[InlineKeyboardButton]:
    """Contact-admin row, omitted when no username is configured.

    Telegram rejects a button whose URL is just https://t.me/, so an unset
    NURFX_ADMIN_TELEGRAM_USERNAME must drop the row rather than build one.
    """
    username = settings.NURFX_ADMIN_TELEGRAM_USERNAME
    if not username:
        return []
    return [InlineKeyboardButton(text=label.format(username=username), url=f"https://t.me/{username}")]


def main_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [SITE_BUTTON],
        [InlineKeyboardButton(text="💳 Token sotib olish (Rekvizitlar)", callback_data="buy_tokens")],
    ]
    admin_row = _admin_button("💬 Admin bilan bog'lanish")
    if admin_row:
        rows.append(admin_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def website_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[SITE_BUTTON]])


@sync_to_async
def _register_telegram_user(telegram_id: int, full_name: str):
    from apps.authentication.services import get_or_create_telegram_user

    user, created = get_or_create_telegram_user(telegram_id, full_name)
    return user.tokens_balance, created


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    # /start is also the way out of a half-finished analysis conversation.
    await state.clear()

    telegram_id = message.from_user.id
    balance, created = await _register_telegram_user(
        telegram_id, message.from_user.full_name or ""
    )

    cost = settings.NURFX_ANALYSIS_TOKEN_COST
    text = "<b>Assalomu alaykum! NurFX.ai botiga xush kelibsiz.</b>\n\n"

    if created:
        text += (
            f"🎁 Sovg'a sifatida <b>{settings.NURFX_WELCOME_TOKENS} token</b> "
            f"berildi — bu <b>{settings.NURFX_WELCOME_TOKENS // cost} ta bepul tahlil</b>.\n\n"
        )

    text += (
        f"📸 <b>Tahlil qilish uchun grafik skrinshotini shu yerga yuboring.</b>\n"
        f"Keyin juftlik, timeframe va strategiyani tanlaysiz.\n\n"
        f"💰 Balansingiz: <b>{balance}</b> token\n"
        f"📊 Mavjud tahlillar: <b>{balance // cost}</b> ta "
        f"<i>(har biri {cost} token)</i>\n\n"
        f"<b>Buyruqlar:</b>\n"
        f"/buy — Token sotib olish\n"
        f"/redeem KOD — Kuponni faollashtirish\n"
        f"/balance — Balansni tekshirish\n"
        f"/cancel — Joriy tahlilni bekor qilish"
    )

    if _is_admin(telegram_id):
        text += (
            "\n\n👨‍💻 <b>Admin:</b>\n"
            "<code>/generate_coupon tokens=21 price=168000</code>"
        )

    await message.answer(text, parse_mode="HTML", reply_markup=main_keyboard())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    from apps.bot.analysis_flow import discard_state_image

    await discard_state_image(state)
    await state.clear()
    await message.answer("❌ Bekor qilindi. Token yechilmadi.")


@router.message(Command("buy"))
async def cmd_buy(message: Message):
    await send_payment_info(message)


@router.callback_query(F.data == "buy_tokens")
async def cb_buy_tokens(callback: CallbackQuery):
    await send_payment_info(callback.message)
    await callback.answer()


async def send_payment_info(message: Message):
    from django.conf import settings as django_settings
    card_number = django_settings.NURFX_PAYMENT_CARD_NUMBER
    card_holder = django_settings.NURFX_PAYMENT_CARD_HOLDER
    admin_username = django_settings.NURFX_ADMIN_TELEGRAM_USERNAME

    text = (
        f"💎 <b>NurFX.ai Token Paketlari va Xarid Qilish</b>\n\n"
        f"📦 <b>BASIC:</b> 30 token — <b>210,000 UZS</b> <i>(10 ta tahlil)</i>\n"
        f"📦 <b>PRO:</b> 90 token — <b>540,000 UZS</b> <i>(30 ta tahlil)</i> ⭐ <b>Ommabop</b>\n"
        f"📦 <b>VIP MAX:</b> 210 token — <b>1,197,000 UZS</b> <i>(70 ta tahlil)</i>\n\n"
        f"💳 <b>To'lov rekvizitlari:</b>\n"
        f"Karta raqami: <code>{card_number}</code>\n"
        f"Egasining ismi: <b>{card_holder}</b>\n\n"
        f"📲 <b>To'lovdan so'ng:</b>\n"
        f"1. To'lov chekini @{admin_username} ga yuboring.\n"
        f"2. Admin sizga taqdim etgan kupon kodini botda <code>/redeem KOD</code> orqali faollashtirasiz!\n"
        f"3. Tokenlar balansingizga qo'shiladi va <b>nurfxai.uz</b> saytida ishlatasiz."
    )

    rows = []
    admin_row = _admin_button("💬 Chekni Adminga yuborish (@{username})")
    if admin_row:
        rows.append(admin_row)
    rows.append([SITE_BUTTON])

    await message.answer(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


@router.message(Command("generate_coupon"))
async def cmd_generate_coupon(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("Unauthorized.")
        return

    text = message.text.strip()
    match = COUPON_PATTERN.match(text)
    if not match:
        await message.answer(
            "Invalid format.\nUsage: /generate_coupon tokens=21 price=168000"
        )
        return

    token_amount = int(match.group(1))
    custom_price_uzs = int(match.group(2))

    try:
        coupon = await _create_coupon(token_amount, custom_price_uzs)
        await message.answer(
            f"<b>Kupon yaratildi!</b>\n\n"
            f"🔑 Kod: <code>{coupon.code}</code>\n"
            f"🪙 Tokenlar: {coupon.token_amount} ta\n"
            f"💵 Narxi: {coupon.custom_price_uzs:,} UZS\n\n"
            f"<i>Bir martalik kupon.</i>",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.exception("Coupon generation failed")
        await message.answer(f"Error: {exc}")


@router.message(Command("redeem"))
async def cmd_redeem(message: Message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Foydalanish: /redeem NURFX-8000-XXXX")
        return

    code = parts[1].strip().upper()
    result, info = await _redeem_coupon_for_telegram_user(message.from_user.id, code)

    if result is None:
        await message.answer(f"❌ Kupon aktivlashmadi: {info}")
    else:
        await message.answer(
            f"🎉 <b>Kupon faollashtirildi!</b>\n\n"
            f"➕ Qushildi: <b>{result.token_amount}</b> token\n"
            f"💰 Yangi balans: <b>{info}</b> token\n\n"
            f"🌐 Endi <b>nurfxai.uz</b> saytida tahlil qilishingiz mumkin!",
            parse_mode="HTML",
            reply_markup=website_keyboard(),
        )


@sync_to_async
def _get_balance(telegram_id: int):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        user = User.objects.get(telegram_id=telegram_id)
        return user.tokens_balance
    except User.DoesNotExist:
        return None


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    balance = await _get_balance(message.from_user.id)
    if balance is None:
        await message.answer(
            "⚠️ Hisobingiz topilmadi. /start buyrug'ini yuboring.",
            parse_mode="HTML",
        )
        return

    cost = settings.NURFX_ANALYSIS_TOKEN_COST
    await message.answer(
        f"💰 Token balansingiz: <b>{balance}</b> token\n"
        f"📊 Mavjud tahlillar: <b>{balance // cost}</b> ta\n\n"
        f"📸 Tahlil uchun grafik skrinshotini yuboring.",
        parse_mode="HTML",
    )


def create_bot() -> tuple[Bot, Dispatcher]:
    from aiogram.client.default import DefaultBotProperties
    from aiogram.fsm.storage.redis import RedisStorage

    from apps.bot import analysis_flow

    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    # Redis-backed FSM so a bot restart mid-conversation doesn't strand users
    # halfway through picking a pair.
    dp = Dispatcher(storage=RedisStorage.from_url(settings.BOT_FSM_REDIS_URL))

    # Command handlers first: /start and /cancel must win over the catch-all
    # message handler that reads a custom currency pair.
    dp.include_router(router)
    dp.include_router(analysis_flow.router)
    return bot, dp
