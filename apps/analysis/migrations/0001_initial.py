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
            name="Analysis",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("currency_pair", models.CharField(db_index=True, max_length=16)),
                ("timeframe", models.CharField(max_length=16)),
                ("strategy", models.CharField(choices=[("ICT", "Inner Circle Trader"), ("SMC", "Smart Money Concepts")], max_length=8)),
                ("chart_image", models.ImageField(upload_to="charts/%Y/%m/")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("completed", "Completed"), ("failed", "Failed")], db_index=True, default="pending", max_length=16)),
                ("stage1_claude_output", models.JSONField(blank=True, null=True)),
                ("stage2_openai_output", models.JSONField(blank=True, null=True)),
                ("stage3_gemini_output", models.JSONField(blank=True, null=True)),
                ("final_result", models.JSONField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("tokens_deducted", models.PositiveIntegerField(default=0)),
                ("celery_task_id", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="analyses", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name_plural": "analyses",
                "db_table": "analyses",
                "ordering": ["-created_at"],
            },
        ),
    ]
