"""Admin-only reporting commands for the Telegram bot.

Read-only: these commands show who is using the product and how, but never
change balances or accounts — anything that moves tokens stays in the Django
admin, where it is logged and harder to fire by accident.

Every handler re-checks the caller against TELEGRAM_ADMIN_IDS, including the
pagination callbacks: a callback arrives with its own from_user, so trusting
the check that rendered the keyboard would let a forwarded button leak data.
"""
import logging
from datetime import timedelta
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

router = Router()

PAGE_SIZE = 8


def _is_admin(telegram_id: int) -> bool:
    return str(telegram_id) in settings.TELEGRAM_ADMIN_IDS


def _fmt_uzs(amount) -> str:
    return f"{amount or 0:,}".replace(",", " ")


def _when(dt) -> str:
    if not dt:
        return "—"
    return timezone.localtime(dt).strftime("%d.%m.%Y %H:%M")


def _label(user) -> str:
    """Prefer a real name, fall back to the telegram id, then the address."""
    if user.full_name:
        return escape(user.full_name)
    if user.telegram_id:
        return f"TG {user.telegram_id}"
    return escape(user.email)


# ---------------------------------------------------------------- /stats ---
@sync_to_async
def _collect_stats() -> dict:
    from apps.analysis.models import Analysis
    from apps.tokens.models import TokenCoupon, TokenTransaction

    User = get_user_model()
    now = timezone.now()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    analyses = Analysis.objects.all()
    signals = (
        analyses.filter(status=Analysis.Status.COMPLETED)
        .exclude(final_result=None)
        .values("final_result__signal")
        .annotate(n=Count("id"))
    )

    return {
        "users": User.objects.count(),
        "users_day": User.objects.filter(created_at__gte=day_ago).count(),
        "users_week": User.objects.filter(created_at__gte=week_ago).count(),
        "analyses": analyses.count(),
        "analyses_day": analyses.filter(created_at__gte=day_ago).count(),
        "completed": analyses.filter(status=Analysis.Status.COMPLETED).count(),
        "failed": analyses.filter(status=Analysis.Status.FAILED).count(),
        "running": analyses.filter(
            status__in=[Analysis.Status.PENDING, Analysis.Status.PROCESSING]
        ).count(),
        "signals": {row["final_result__signal"] or "—": row["n"] for row in signals},
        "balance_total": User.objects.aggregate(s=Sum("tokens_balance"))["s"] or 0,
        "spent": abs(
            TokenTransaction.objects.filter(
                transaction_type=TokenTransaction.Type.ANALYSIS_DEDUCTION
            ).aggregate(s=Sum("token_amount"))["s"]
            or 0
        ),
        "coupons_active": TokenCoupon.objects.filter(is_used=False).count(),
        "coupons_used": TokenCoupon.objects.filter(is_used=True).count(),
        "revenue": TokenCoupon.objects.filter(is_used=True).aggregate(
            s=Sum("custom_price_uzs")
        )["s"]
        or 0,
    }


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not _is_admin(message.from_user.id):
        return

    s = await _collect_stats()
    signals = "\n".join(
        f"   • {escape(str(k))}: <b>{v}</b>" for k, v in sorted(s["signals"].items())
    ) or "   • —"

    await message.answer(
        f"📊 <b>NurFX.ai — Statistika</b>\n\n"
        f"👥 <b>Foydalanuvchilar:</b> {s['users']}\n"
        f"   • Bugun: +{s['users_day']}   • 7 kunda: +{s['users_week']}\n\n"
        f"🔍 <b>Tahlillar:</b> {s['analyses']}\n"
        f"   • Bugun: {s['analyses_day']}\n"
        f"   • Muvaffaqiyatli: {s['completed']}   • Xato: {s['failed']}"
        f"   • Jarayonda: {s['running']}\n\n"
        f"📈 <b>Signallar:</b>\n{signals}\n\n"
        f"🪙 <b>Tokenlar:</b>\n"
        f"   • Qo'llarda: {s['balance_total']}\n"
        f"   • Sarflangan: {s['spent']}\n\n"
        f"🎟 <b>Kuponlar:</b> {s['coupons_used']} ishlatilgan, "
        f"{s['coupons_active']} faol\n"
        f"💵 <b>Tushum:</b> {_fmt_uzs(s['revenue'])} UZS\n\n"
        f"<i>/users — foydalanuvchilar ro'yxati</i>",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------- /users ---
@sync_to_async
def _list_users(page: int) -> tuple[list[dict], int, int]:
    User = get_user_model()
    total = User.objects.count()
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))

    rows = (
        User.objects.annotate(n_analyses=Count("analyses"))
        .order_by("-created_at")[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    )
    return (
        [
            {
                "label": _label(u),
                "balance": u.tokens_balance,
                "analyses": u.n_analyses,
                "joined": _when(u.created_at),
                "tg": u.telegram_id,
                "staff": u.is_staff,
            }
            for u in rows
        ],
        page,
        pages,
    )


def _render_users(rows: list[dict], page: int, pages: int) -> tuple[str, InlineKeyboardMarkup | None]:
    if not rows:
        return "👥 Hali foydalanuvchi yo'q.", None

    lines = [f"👥 <b>Foydalanuvchilar</b>  <i>({page + 1}/{pages})</i>", ""]
    for r in rows:
        badge = " 👑" if r["staff"] else ""
        lines.append(
            f"<b>{r['label']}</b>{badge}\n"
            f"   🪙 {r['balance']} token · 🔍 {r['analyses']} tahlil\n"
            f"   📅 {r['joined']}"
            + (f" · <code>/user {r['tg']}</code>" if r["tg"] else "")
        )
        lines.append("")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"adm:users:{page - 1}"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"adm:users:{page + 1}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[nav]) if nav else None
    return "\n".join(lines).strip(), keyboard


@router.message(Command("users"))
async def cmd_users(message: Message):
    if not _is_admin(message.from_user.id):
        return

    rows, page, pages = await _list_users(0)
    text, keyboard = _render_users(rows, page, pages)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("adm:users:"))
async def on_users_page(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return

    page = int(callback.data.rsplit(":", 1)[1])
    rows, page, pages = await _list_users(page)
    text, keyboard = _render_users(rows, page, pages)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ----------------------------------------------------------------- /user ---
@sync_to_async
def _user_detail(query: str) -> str | None:
    from apps.analysis.models import Analysis
    from apps.tokens.models import TokenTransaction

    User = get_user_model()

    user = None
    if query.isdigit():
        user = User.objects.filter(telegram_id=int(query)).first()
    if user is None:
        user = User.objects.filter(email__iexact=query).first()
    if user is None:
        user = User.objects.filter(full_name__icontains=query).first()
    if user is None:
        return None

    analyses = Analysis.objects.filter(user=user)
    recent = analyses.order_by("-created_at")[:5]
    txs = TokenTransaction.objects.filter(user=user).order_by("-created_at")[:5]

    lines = [
        f"👤 <b>{_label(user)}</b>",
        "",
        f"📧 <code>{escape(user.email)}</code>",
        f"🆔 Telegram: <code>{user.telegram_id or '—'}</code>",
        f"🪙 Balans: <b>{user.tokens_balance}</b> token",
        f"📅 Ro'yxatdan: {_when(user.created_at)}",
        f"🕐 Oxirgi faollik: {_when(user.last_login_at)}",
        f"🔍 Jami tahlil: <b>{analyses.count()}</b>",
        "",
    ]

    if recent:
        lines.append("<b>Oxirgi tahlillar:</b>")
        for a in recent:
            signal = (a.final_result or {}).get("signal", a.get_status_display())
            lines.append(
                f"• {escape(a.currency_pair)} {escape(a.timeframe)} — "
                f"{escape(str(signal))} <i>({_when(a.created_at)})</i>"
            )
        lines.append("")

    if txs:
        lines.append("<b>Oxirgi tranzaksiyalar:</b>")
        for t in txs:
            sign = "+" if t.token_amount >= 0 else ""
            lines.append(
                f"• {sign}{t.token_amount} — {escape(t.get_transaction_type_display())}"
                f" <i>({_when(t.created_at)})</i>"
            )

    return "\n".join(lines)


@router.message(Command("user"))
async def cmd_user(message: Message):
    if not _is_admin(message.from_user.id):
        return

    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Foydalanish: <code>/user 123456789</code> "
            "(Telegram ID, email yoki ism)",
            parse_mode="HTML",
        )
        return

    detail = await _user_detail(parts[1].strip())
    if detail is None:
        await message.answer("❌ Foydalanuvchi topilmadi.")
        return

    await message.answer(detail, parse_mode="HTML")
