"""Push a finished analysis back to Telegram from the Celery worker.

The worker is a plain synchronous process, so this talks to the Bot API over
HTTP rather than pulling aiogram and an event loop into the task.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT_SECONDS = 15


def send_telegram_message(chat_id: int, text: str) -> bool:
    """Best-effort delivery. Returns True on success, never raises."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN unset; cannot notify chat %s", chat_id)
        return False

    try:
        response = requests.post(
            TELEGRAM_API.format(token=token),
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            logger.warning(
                "Telegram rejected message to %s: %s %s",
                chat_id,
                response.status_code,
                response.text[:300],
            )
            return False
        return True
    except requests.RequestException:
        # Delivery is a side effect of a completed analysis — the result is
        # already saved, so a network blip here must not fail the task.
        logger.exception("Could not reach Telegram for chat %s", chat_id)
        return False


def notify_analysis_complete(analysis) -> None:
    from apps.bot.formatting import format_analysis_result

    if not analysis.telegram_chat_id:
        return

    text = format_analysis_result(
        analysis.final_result or {},
        analysis.currency_pair,
        analysis.timeframe,
        analysis.strategy,
    )
    send_telegram_message(analysis.telegram_chat_id, text)


def notify_analysis_failed(analysis, refunded: bool) -> None:
    if not analysis.telegram_chat_id:
        return

    text = (
        f"❌ <b>{analysis.currency_pair} · {analysis.timeframe}</b> tahlili "
        "amalga oshmadi.\n\n"
    )
    if refunded:
        text += (
            f"💰 <b>{settings.NURFX_ANALYSIS_TOKEN_COST} token</b> balansingizga "
            "qaytarildi.\n\n"
        )
    text += "Iltimos, birozdan so'ng qayta urinib ko'ring."

    send_telegram_message(analysis.telegram_chat_id, text)
