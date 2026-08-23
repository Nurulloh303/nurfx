import asyncio
import logging
from django.core.management.base import BaseCommand
from apps.bot.handlers import create_bot

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the NurFX Telegram bot"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting NurFX Telegram bot..."))
        bot, dp = create_bot()
        try:
            asyncio.run(dp.start_polling(bot))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Bot stopped by user."))
