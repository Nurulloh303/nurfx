from django.conf import settings
from django.http import FileResponse, Http404
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.tokens.services import InsufficientTokensError, deduct_analysis_tokens

from .models import Analysis
from .serializers import AnalysisCreateSerializer, AnalysisDetailSerializer, AnalysisListSerializer


@method_decorator(ratelimit(key="user", rate="5/m", method="POST", block=True), name="dispatch")
class RunAnalysisView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "analysis"
    serializer_class = AnalysisCreateSerializer

    def post(self, request):
        serializer = AnalysisCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if request.user.tokens_balance < settings.NURFX_ANALYSIS_TOKEN_COST:
            return Response(
                {
                    "success": False,
                    "error": "Insufficient tokens.",
                    "required": settings.NURFX_ANALYSIS_TOKEN_COST,
                    "available": request.user.tokens_balance,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        analysis = Analysis.objects.create(
            user=request.user,
            currency_pair=serializer.validated_data["currency_pair"],
            timeframe=serializer.validated_data["timeframe"],
            strategy=serializer.validated_data["strategy"],
            chart_image=serializer.validated_data["chart_image"],
            status=Analysis.Status.PENDING,
        )

        try:
            remaining = deduct_analysis_tokens(request.user, str(analysis.id))
            analysis.tokens_deducted = settings.NURFX_ANALYSIS_TOKEN_COST
            analysis.save(update_fields=["tokens_deducted"])
        except InsufficientTokensError as exc:
            analysis.delete()
            return Response({"success": False, "error": str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)

        from apps.ai_engine.tasks import run_ai_pipeline

        task = run_ai_pipeline.delay(str(analysis.id))
        analysis.celery_task_id = task.id
        analysis.status = Analysis.Status.PROCESSING
        analysis.save(update_fields=["celery_task_id", "status"])

        return Response(
            {
                "success": True,
                "message": "Analysis queued. Poll /analysis/<id>/ for results.",
                "analysis_id": str(analysis.id),
                "task_id": task.id,
                "tokens_remaining": remaining,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class AnalysisHistoryView(ListAPIView):
    serializer_class = AnalysisListSerializer

    def get_queryset(self):
        return Analysis.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"success": True, "analyses": response.data})


class AnalysisDetailView(RetrieveAPIView):
    serializer_class = AnalysisDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Analysis.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({"success": True, "analysis": serializer.data})


class AnalysisChartImageView(APIView):
    """
    Serve the chart image only to the analysis owner. Chart images must
    never be reachable directly via the public MEDIA_URL — screenshots can
    contain broker account details, balances, or other sensitive info, and
    the upload path is otherwise guessable-by-brute-force over time.
    """

    @extend_schema(responses={(200, "image/png"): OpenApiTypes.BINARY})
    def get(self, request, id):
        try:
            analysis = Analysis.objects.get(id=id, user=request.user)
        except Analysis.DoesNotExist:
            raise Http404
        if not analysis.chart_image:
            raise Http404
        return FileResponse(analysis.chart_image.open("rb"), content_type="image/png")
