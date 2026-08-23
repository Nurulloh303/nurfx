from django.contrib import admin

from .models import Analysis


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ("currency_pair", "timeframe", "strategy", "user", "status", "created_at", "completed_at")
    list_filter = ("status", "strategy", "timeframe")
    search_fields = ("user__email", "currency_pair")
    readonly_fields = (
        "id", "run_metadata", "final_result", "celery_task_id",
        "created_at", "completed_at",
    )
    ordering = ("-created_at",)
