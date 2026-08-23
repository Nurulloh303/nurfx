from rest_framework import serializers

from .image_processor import sanitize_chart_image
from .models import Analysis


class AnalysisCreateSerializer(serializers.ModelSerializer):
    chart_image = serializers.ImageField()

    class Meta:
        model = Analysis
        fields = ("currency_pair", "timeframe", "strategy", "chart_image")

    def validate_currency_pair(self, value):
        value = value.strip().upper()
        allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/")
        if not value or not all(c in allowed_chars for c in value):
            raise serializers.ValidationError("Invalid currency pair format.")
        if len(value) > 16:
            raise serializers.ValidationError("Currency pair too long.")
        return value

    def validate_timeframe(self, value):
        allowed = {"M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN"}
        value = value.strip().upper()
        if value not in allowed:
            raise serializers.ValidationError(f"Invalid timeframe. Allowed: {', '.join(sorted(allowed))}")
        return value

    def validate_strategy(self, value):
        value = value.strip().upper()
        if value not in Analysis.Strategy.values:
            raise serializers.ValidationError(f"Strategy must be one of: {', '.join(Analysis.Strategy.values)}")
        return value

    def validate_chart_image(self, value):
        return sanitize_chart_image(value)


class AnalysisListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = (
            "id",
            "currency_pair",
            "timeframe",
            "strategy",
            "status",
            "tokens_deducted",
            "created_at",
            "completed_at",
        )
        read_only_fields = fields


class AnalysisDetailSerializer(serializers.ModelSerializer):
    chart_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Analysis
        fields = (
            "id",
            "currency_pair",
            "timeframe",
            "strategy",
            "chart_image_url",
            "status",
            "final_result",
            "error_message",
            "tokens_deducted",
            "created_at",
            "completed_at",
        )
        read_only_fields = fields

    def get_chart_image_url(self, obj) -> str:
        from django.urls import reverse

        url = reverse("analysis-image", kwargs={"id": obj.id})
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url
