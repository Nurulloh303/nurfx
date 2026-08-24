import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="ai_engine.run_pipeline",
    queue="ai_pipeline",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def run_ai_pipeline(self, analysis_id: str):
    from apps.analysis.models import Analysis
    from apps.ai_engine.pipeline import AnalysisRefused, analyze_chart

    try:
        analysis = Analysis.objects.select_related("user").get(id=analysis_id)
    except Analysis.DoesNotExist:
        logger.error("Analysis %s not found", analysis_id)
        return {"error": "Analysis not found"}

    analysis.status = Analysis.Status.PROCESSING
    analysis.save(update_fields=["status"])

    try:
        metadata, final = analyze_chart(
            image_path=analysis.chart_image.path,
            currency_pair=analysis.currency_pair,
            timeframe=analysis.timeframe,
            strategy=analysis.strategy,
        )

        analysis.run_metadata = metadata
        analysis.final_result = final
        analysis.status = Analysis.Status.COMPLETED
        analysis.completed_at = timezone.now()
        analysis.save(
            update_fields=["run_metadata", "final_result", "status", "completed_at"]
        )

        logger.info("Analysis %s completed: %s", analysis_id, final.get("signal"))

        from apps.bot.notifications import notify_analysis_complete

        notify_analysis_complete(analysis)
        return {"analysis_id": analysis_id, "status": "completed"}

    except AnalysisRefused as exc:
        # A refusal is a decision about the content, not a transient fault —
        # retrying the identical request would only be declined again.
        logger.warning("Analysis %s refused: %s", analysis_id, exc)
        _mark_failed(analysis, str(exc), final_attempt=True)
        return {"analysis_id": analysis_id, "status": "failed", "error": str(exc)}

    except Exception as exc:
        logger.exception("Analysis %s failed", analysis_id)
        last_attempt = self.request.retries >= self.max_retries
        _mark_failed(analysis, str(exc), final_attempt=last_attempt)

        if not last_attempt:
            raise self.retry(exc=exc)
        return {"analysis_id": analysis_id, "status": "failed", "error": str(exc)}


def _mark_failed(analysis, message: str, final_attempt: bool) -> None:
    analysis.status = analysis.Status.FAILED
    analysis.error_message = message[:2000]
    analysis.completed_at = timezone.now()
    analysis.save(update_fields=["status", "error_message", "completed_at"])

    if not final_attempt:
        # A retry is still coming; don't refund or notify yet.
        return

    refunded = _refund_once(analysis)

    from apps.bot.notifications import notify_analysis_failed

    notify_analysis_failed(analysis, refunded)


def _refund_once(analysis) -> bool:
    """Return the tokens for an analysis that will never produce a result."""
    if analysis.tokens_refunded or not analysis.tokens_deducted:
        return False

    from apps.tokens.services import refund_analysis_tokens

    try:
        refund_analysis_tokens(analysis.user, str(analysis.id))
    except Exception:
        logger.exception("Refund failed for analysis %s", analysis.id)
        return False

    analysis.tokens_refunded = True
    analysis.save(update_fields=["tokens_refunded"])
    return True
