"""
Standalone Telegram bot runner.
Usage: python -m apps.bot.runner
"""
import asyncio
import logging
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.bot.handlers import create_bot  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    bot, dp = create_bot()
    logger.info("NurFX.ai Telegram bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
