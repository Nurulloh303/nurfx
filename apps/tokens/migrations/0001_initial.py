import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TokenCoupon",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.CharField(db_index=True, max_length=32, unique=True)),
                ("token_amount", models.PositiveIntegerField()),
                ("custom_price_uzs", models.PositiveIntegerField()),
                ("is_used", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("used_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="redeemed_coupons", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "token_coupons",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TokenTransaction",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("transaction_type", models.CharField(choices=[("welcome_bonus", "Welcome Bonus"), ("coupon_redemption", "Coupon Redemption"), ("subscription_purchase", "Subscription Purchase"), ("analysis_deduction", "Analysis Deduction"), ("admin_adjustment", "Admin Adjustment")], max_length=32)),
                ("token_amount", models.IntegerField(help_text="Positive for credit, negative for debit")),
                ("description", models.CharField(blank=True, max_length=512)),
                ("package_name", models.CharField(blank=True, max_length=32)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("coupon", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transactions", to="tokens.tokencoupon")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="token_transactions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "token_transactions",
                "ordering": ["-created_at"],
            },
        ),
    ]
