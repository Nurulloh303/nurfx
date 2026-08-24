"""Render an analysis result as a Telegram HTML message.

Shared by the bot (for immediate replies) and the Celery worker (which posts
the finished analysis back to the chat), so both channels word things the same.
"""
from html import escape

SIGNAL_LABEL = {
    "BUY": "🟢 <b>BUY</b> (sotib olish)",
    "SELL": "🔴 <b>SELL</b> (sotish)",
    "NO_TRADE": "⚪️ <b>SAVDO YO'Q</b>",
}

BIAS_LABEL = {
    "bullish": "o'sish tomon",
    "bearish": "tushish tomon",
    "neutral": "aniq emas",
}


def _price(value) -> str:
    """Render a price the user can copy straight into a trading terminal.

    No thousands separator — a comma reads as a decimal point in half the
    world, and a pasted "2,612.50" is not a number any platform accepts.
    Trailing zeros are trimmed but never below two decimals, so gold shows as
    2612.50 rather than 2612.5 while FX keeps its full 1.08453.
    """
    if value is None:
        return "—"
    if not isinstance(value, (int, float)):
        return escape(str(value))

    whole, _, frac = f"{value:.5f}".rstrip("0").partition(".")
    return f"{whole}.{frac.ljust(2, '0')}"


def format_analysis_result(final: dict, pair: str, timeframe: str, strategy: str) -> str:
    signal = final.get("signal", "NO_TRADE")
    lines = [
        f"📊 <b>{escape(pair)}</b> · {escape(timeframe)} · {escape(strategy)}",
        "",
        SIGNAL_LABEL.get(signal, escape(signal)),
    ]

    if signal == "NO_TRADE":
        reason = final.get("rejection_reason") or "Ishonchli setap topilmadi."
        lines += ["", f"<b>Sabab:</b> {escape(str(reason))}"]
    else:
        zone = final.get("entry_zone") or {}
        lines += [
            "",
            f"🎯 <b>Kirish:</b> {_price(zone.get('low'))} — {_price(zone.get('high'))}",
            f"🛑 <b>Stop Loss:</b> {_price(final.get('stop_loss'))}",
            f"✅ <b>TP 1:</b> {_price(final.get('take_profit_1'))}",
            f"✅ <b>TP 2:</b> {_price(final.get('take_profit_2'))}",
            f"⚖️ <b>Risk/Foyda:</b> {escape(str(final.get('risk_reward_ratio', '—')))}",
        ]

    bias = BIAS_LABEL.get(final.get("bias", ""), final.get("bias", "—"))
    confidence = final.get("confidence_score")
    lines += [
        "",
        f"📈 <b>Yo'nalish:</b> {escape(str(bias))}",
        f"💡 <b>Ishonch darajasi:</b> {confidence}/100" if confidence is not None else "",
    ]

    summary = final.get("analysis_summary")
    if summary:
        lines += ["", f"<b>Tahlil:</b>\n{escape(str(summary))}"]

    levels = final.get("key_levels") or []
    if levels:
        lines += ["", "<b>Muhim darajalar:</b>"]
        for lvl in levels[:6]:
            lines.append(
                f"• {escape(str(lvl.get('type', '')))} {_price(lvl.get('price'))}"
                f" — {escape(str(lvl.get('description', '')))}"
            )

    warnings = final.get("warnings") or []
    if warnings:
        lines += ["", "⚠️ <b>Ogohlantirishlar:</b>"]
        lines += [f"• {escape(str(w))}" for w in warnings[:5]]

    lines += [
        "",
        "<i>Bu moliyaviy maslahat emas. Qaror sizniki, riskni o'zingiz boshqarasiz.</i>",
    ]

    return "\n".join(line for line in lines if line != "")
