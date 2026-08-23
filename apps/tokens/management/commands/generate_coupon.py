from django.core.management.base import BaseCommand, CommandError

from apps.tokens.services import create_coupon


class Command(BaseCommand):
    help = "Generate a single-use token coupon (admin utility)."

    def add_arguments(self, parser):
        parser.add_argument("--tokens", type=int, required=True, help="Number of tokens")
        parser.add_argument("--price", type=int, required=True, help="Custom price in UZS")

    def handle(self, *args, **options):
        try:
            coupon = create_coupon(options["tokens"], options["price"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Coupon created: {coupon.code}"))
        self.stdout.write(f"  Tokens: {coupon.token_amount}")
        self.stdout.write(f"  Price:  {coupon.custom_price_uzs:,} UZS")
