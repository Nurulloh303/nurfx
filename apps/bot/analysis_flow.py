"""Chart analysis conversation for the Telegram bot.

Temporary primary channel while the web frontend is being built. It reuses the
same models, token services, and Celery pipeline as the REST API — nothing here
is a parallel implementation, so the web flow keeps working unchanged and this
module can be deleted once the site takes over.

Flow: user sends a chart image -> pick pair -> pick timeframe -> pick strategy
-> tokens deducted, analysis queued. The worker delivers the result back to the
chat (see apps/bot/notifications.py), so the user is not kept waiting on a
polling loop.
"""
import logging
import uuid
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from asgiref.sync import sync_to_async
from django.conf import settings

logger = logging.getLogger(__name__)

router = Router()

TEMP_DIR = Path(settings.MEDIA_ROOT) / "temp_charts"

COMMON_PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "GBPJPY"]
TIMEFRAMES = ["M5", "M15", "M30", "H1", "H4", "D1"]
STRATEGIES = [("ICT", "ICT"), ("SMC", "Smart Money")]

MAX_PAIR_LENGTH = 16
PAIR_ALLOWED_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/")


class AnalysisFlow(StatesGroup):
    pair = State()
    custom_pair = State()
    timeframe = State()
    strategy = State()


def _grid(items, prefix: str, columns: int = 3) -> list[list[InlineKeyboardButton]]:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"{prefix}:{value}")
        for value, label in items
    ]
    return [buttons[i : i + columns] for i in range(0, len(buttons), columns)]


def pair_keyboard() -> InlineKeyboardMarkup:
    rows = _grid([(p, p) for p in COMMON_PAIRS], "pair")
    rows.append([InlineKeyboardButton(text="✍️ Boshqa juftlik", callback_data="pair:__custom__")])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="an:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timeframe_keyboard() -> InlineKeyboardMarkup:
    rows = _grid([(t, t) for t in TIMEFRAMES], "tf")
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="an:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def strategy_keyboard() -> InlineKeyboardMarkup:
    rows = _grid(STRATEGIES, "st", columns=2)
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="an:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --------------------------------------------------------------------------
# Database helpers — every ORM call has to leave the event loop.
# --------------------------------------------------------------------------
@sync_to_async
def _get_user(telegram_id: int):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(telegram_id=telegram_id).first()


@sync_to_async
def _sanitize_to_temp(raw: bytes, filename: str) -> str:
    """Run the upload through the same sanitizer the REST API uses."""
    from django.core.files.base import ContentFile

    from apps.analysis.image_processor import sanitize_chart_image

    cleaned = sanitize_chart_image(ContentFile(raw, name=filename))

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_DIR / f"{uuid.uuid4().hex}.png"
    path.write_bytes(cleaned.read())
    return str(path)


@sync_to_async
def _create_and_queue(user_id, chat_id: int, image_path: str, pair: str, timeframe: str, strategy: str):
    """Deduct tokens, persist the analysis, and hand it to Celery.

    Returns (analysis_id, remaining_tokens) or raises InsufficientTokensError.
    """
    from django.core.files.base import ContentFile

    from apps.ai_engine.tasks import run_ai_pipeline
    from apps.analysis.models import Analysis
    from apps.tokens.services import deduct_analysis_tokens

    path = Path(image_path)
    analysis = Analysis.objects.create(
        user_id=user_id,
        currency_pair=pair,
        timeframe=timeframe,
        strategy=strategy,
        chart_image=ContentFile(path.read_bytes(), name=path.name),
        status=Analysis.Status.PENDING,
        telegram_chat_id=chat_id,
    )

    try:
        remaining = deduct_analysis_tokens(analysis.user, str(analysis.id))
    except Exception:
        analysis.delete()
        raise

    analysis.tokens_deducted = settings.NURFX_ANALYSIS_TOKEN_COST
    task = run_ai_pipeline.delay(str(analysis.id))
    analysis.celery_task_id = task.id
    analysis.status = Analysis.Status.PROCESSING
    analysis.save(update_fields=["tokens_deducted", "celery_task_id", "status"])

    # The analysis is already queued and paid for at this point — a temp file
    # that refuses to delete must not surface to the user as a failure.
    _discard_temp(str(path))
    return str(analysis.id), remaining


def _discard_temp(image_path: str | None) -> None:
    if not image_path:
        return
    try:
        Path(image_path).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove temp chart %s", image_path, exc_info=True)


async def discard_state_image(state: FSMContext) -> None:
    """Drop the pending upload behind whatever conversation is in progress."""
    data = await state.get_data()
    _discard_temp(data.get("image_path"))


# --------------------------------------------------------------------------
# Entry point: an image arrives
# --------------------------------------------------------------------------
async def start_analysis(message: Message, state: FSMContext, raw: bytes, filename: str):
    user = await _get_user(message.from_user.id)
    if user is None:
        await message.answer(
            "⚠️ Hisobingiz topilmadi. Avval /start buyrug'ini yuboring.",
            parse_mode="HTML",
        )
        return

    cost = settings.NURFX_ANALYSIS_TOKEN_COST
    if user.tokens_balance < cost:
        await message.answer(
            f"❌ <b>Token yetarli emas.</b>\n\n"
            f"Kerak: <b>{cost}</b> token\n"
            f"Sizda: <b>{user.tokens_balance}</b> token\n\n"
            f"Token sotib olish uchun /buy buyrug'ini yuboring.",
            parse_mode="HTML",
        )
        return

    notice = await message.answer("🔄 Rasm tekshirilmoqda...")

    try:
        image_path = await _sanitize_to_temp(raw, filename)
    except Exception as exc:
        logger.warning("Chart rejected for %s: %s", message.from_user.id, exc)
        await notice.edit_text(
            "❌ Rasmni o'qib bo'lmadi. Grafik skrinshotini PNG yoki JPG "
            "ko'rinishida, 5 MB dan kichik qilib yuboring."
        )
        return

    await state.clear()
    await state.update_data(image_path=image_path)
    await state.set_state(AnalysisFlow.pair)

    await notice.edit_text(
        "📊 <b>1/3 — Qaysi valyuta juftligi?</b>",
        parse_mode="HTML",
        reply_markup=pair_keyboard(),
    )


@router.message(F.photo)
async def on_photo(message: Message, state: FSMContext):
    # Telegram re-compresses photos; the largest size is the least damaged.
    raw = await message.bot.download(message.photo[-1])
    await message.answer(
        "💡 <i>Maslahat: grafikni <b>fayl</b> sifatida yuborsangiz "
        "(qisqichni bosib «File»), narx raqamlari aniqroq o'qiladi.</i>",
        parse_mode="HTML",
    )
    await start_analysis(message, state, raw.read(), "chart.jpg")


@router.message(F.document)
async def on_document(message: Message, state: FSMContext):
    doc = message.document
    if not (doc.mime_type or "").startswith("image/"):
        await message.answer("❌ Faqat rasm fayllari qabul qilinadi (PNG yoki JPG).")
        return
    if doc.file_size and doc.file_size > settings.MAX_CHART_IMAGE_SIZE_BYTES:
        limit = settings.MAX_CHART_IMAGE_SIZE_BYTES // (1024 * 1024)
        await message.answer(f"❌ Fayl juda katta. Chegara: {limit} MB.")
        return

    raw = await message.bot.download(doc)
    await start_analysis(message, state, raw.read(), doc.file_name or "chart.png")


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------
@router.callback_query(F.data == "an:cancel")
async def on_cancel(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _discard_temp(data.get("image_path"))
    await state.clear()
    await callback.message.edit_text("❌ Bekor qilindi. Token yechilmadi.")
    await callback.answer()


@router.callback_query(AnalysisFlow.pair, F.data.startswith("pair:"))
async def on_pair(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]

    if value == "__custom__":
        await state.set_state(AnalysisFlow.custom_pair)
        await callback.message.edit_text(
            "✍️ Juftlik nomini yozing (masalan: <code>USDCHF</code>).",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await state.update_data(pair=value)
    await state.set_state(AnalysisFlow.timeframe)
    await callback.message.edit_text(
        f"📊 <b>{value}</b>\n\n<b>2/3 — Qaysi timeframe?</b>",
        parse_mode="HTML",
        reply_markup=timeframe_keyboard(),
    )
    await callback.answer()


@router.message(AnalysisFlow.custom_pair)
async def on_custom_pair(message: Message, state: FSMContext):
    value = (message.text or "").strip().upper()
    if not value or len(value) > MAX_PAIR_LENGTH or not set(value) <= PAIR_ALLOWED_CHARS:
        await message.answer(
            "❌ Noto'g'ri format. Faqat harf, raqam va «/» ishlating, "
            f"{MAX_PAIR_LENGTH} belgidan oshmasin. Masalan: <code>USDCHF</code>",
            parse_mode="HTML",
        )
        return

    await state.update_data(pair=value)
    await state.set_state(AnalysisFlow.timeframe)
    await message.answer(
        f"📊 <b>{value}</b>\n\n<b>2/3 — Qaysi timeframe?</b>",
        parse_mode="HTML",
        reply_markup=timeframe_keyboard(),
    )


@router.callback_query(AnalysisFlow.timeframe, F.data.startswith("tf:"))
async def on_timeframe(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    await state.update_data(timeframe=value)
    await state.set_state(AnalysisFlow.strategy)

    data = await state.get_data()
    await callback.message.edit_text(
        f"📊 <b>{data['pair']}</b> · {value}\n\n<b>3/3 — Qaysi strategiya?</b>",
        parse_mode="HTML",
        reply_markup=strategy_keyboard(),
    )
    await callback.answer()


@router.callback_query(AnalysisFlow.strategy, F.data.startswith("st:"))
async def on_strategy(callback: CallbackQuery, state: FSMContext):
    from apps.tokens.services import InsufficientTokensError

    strategy = callback.data.split(":", 1)[1]
    data = await state.get_data()
    await state.clear()

    image_path = data.get("image_path")
    if not image_path or not Path(image_path).exists():
        await callback.message.edit_text(
            "❌ Rasm muddati tugadi. Grafikni qaytadan yuboring."
        )
        await callback.answer()
        return

    user = await _get_user(callback.from_user.id)
    if user is None:
        _discard_temp(image_path)
        await callback.message.edit_text("⚠️ Hisobingiz topilmadi. /start yuboring.")
        await callback.answer()
        return

    await callback.message.edit_text("⏳ Tahlil boshlandi...")
    await callback.answer()

    try:
        analysis_id, remaining = await _create_and_queue(
            user.id,
            callback.message.chat.id,
            image_path,
            data["pair"],
            data["timeframe"],
            strategy,
        )
    except InsufficientTokensError:
        _discard_temp(image_path)
        await callback.message.edit_text(
            "❌ Token yetarli emas. /buy orqali to'ldiring."
        )
        return
    except Exception:
        logger.exception("Failed to queue analysis for %s", callback.from_user.id)
        _discard_temp(image_path)
        await callback.message.edit_text(
            "❌ Texnik xatolik. Token yechilmadi, qaytadan urinib ko'ring."
        )
        return

    cost = settings.NURFX_ANALYSIS_TOKEN_COST
    await callback.message.edit_text(
        f"⏳ <b>{data['pair']} · {data['timeframe']} · {strategy}</b>\n\n"
        f"Tahlil qilinmoqda — odatda 1–3 daqiqa oladi.\n"
        f"Tayyor bo'lgach shu yerga yuboraman, kutib o'tirishingiz shart emas.\n\n"
        f"🪙 Yechildi: <b>{cost}</b> token\n"
        f"💰 Qoldi: <b>{remaining}</b> token",
        parse_mode="HTML",
    )
    logger.info("Queued analysis %s from Telegram user %s", analysis_id, callback.from_user.id)
