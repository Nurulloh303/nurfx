import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Analysis(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class Strategy(models.TextChoices):
        ICT = "ICT", "Inner Circle Trader"
        SMC = "SMC", "Smart Money Concepts"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="analyses",
    )

    currency_pair = models.CharField(max_length=16, db_index=True)
    timeframe = models.CharField(max_length=16)
    strategy = models.CharField(max_length=8, choices=Strategy.choices)

    chart_image = models.ImageField(upload_to="charts/%Y/%m/")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)

    # How the model run went: model served, tool calls, token usage.
    run_metadata = models.JSONField(null=True, blank=True)
    final_result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    tokens_deducted = models.PositiveIntegerField(default=0)
    celery_task_id = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "analyses"
        ordering = ["-created_at"]
        verbose_name_plural = "analyses"

    def __str__(self):
        return f"{self.currency_pair} {self.timeframe} [{self.status}] — {self.user.email}"
