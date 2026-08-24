"""
Single-call chart analysis on Claude Opus 5.

One vision request replaces the previous three-provider pipeline. Opus 5 reads
the chart, validates the setup against the risk rules, and emits the final JSON
in one turn. Before answering it may call `zoom_chart_region` a few times to
re-read price labels at full resolution — cropping and looking again is a
cheaper way to get accurate levels than spending more thinking tokens on a
downscaled image.
"""
import base64
import io
import json
import logging
from pathlib import Path

from django.conf import settings
from PIL import Image

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
ZOOM_OUTPUT_LONG_EDGE = 1400


class AnalysisError(Exception):
    """The model could not produce a usable analysis."""


class AnalysisRefused(AnalysisError):
    """Safety classifiers declined the request."""


SYSTEM_PROMPT = """You are the chart analyst for NurFX.ai. You read a single \
trading chart screenshot and return one ICT/SMC trade setup as JSON.

What to identify:
- Liquidity sweeps, order blocks (OB), fair value gaps (FVG)
- Market structure shifts (MSS) and key support/resistance
- Overall bias: bullish, bearish, or neutral

What the setup must satisfy before you signal BUY or SELL:
- Entry sits at a valid institutional level — an OB, an FVG, or a liquidity sweep
- Stop loss sits behind the structure or wick that would invalidate the idea
- Reward-to-risk is at least 1:2 measured to take_profit_1
- Every price is consistent with the levels actually visible on the chart

If any of those fail, return signal NO_TRADE and put the reason in \
rejection_reason. A NO_TRADE with a clear reason is a correct answer, not a \
failure — do not stretch a weak setup to produce a signal.

Reading prices: the chart's price axis is the only source of truth for levels. \
Where a label is too small to read confidently, zoom into it rather than \
estimating. Quote prices at the instrument's normal precision (XAUUSD to two \
decimals, most FX pairs to four or five).

Scope: analyse the chart you were given. Do not assume news events, positions, \
or higher-timeframe context that is not visible in the image; where the missing \
context matters, say so in warnings.

confidence_score is 0-100 and reflects how well the chart supports the setup — \
a clean sweep into an untested OB with room to target is high, a marginal setup \
read off an unclear chart is low.

analysis_summary is for the trader: two or three plain sentences on what the \
chart shows and why this setup follows from it. No headings, no restating the \
JSON fields."""


LANGUAGE_INSTRUCTION = """

Language: write every free-text field — analysis_summary, each \
key_levels[].description, every entry in warnings, and rejection_reason — in \
{language}. Keep ICT/SMC terminology (order block, FVG, MSS, liquidity sweep, \
BOS) and instrument names in their usual English form; traders read and say \
them that way, and translating them makes the analysis harder to follow. \
Prices stay as digits. Enum fields (signal, bias) keep their schema values."""


def build_system_prompt() -> str:
    """Assemble the cached prefix. Constant per deployment, so it stays cached."""
    return SYSTEM_PROMPT + LANGUAGE_INSTRUCTION.format(
        language=settings.AI_OUTPUT_LANGUAGE
    )


ZOOM_TOOL = {
    "name": "zoom_chart_region",
    "description": (
        "Crop a rectangular region out of the chart and return it enlarged. "
        "Call this when you need to read a price-axis label, candle wick, or "
        "level precisely and the full-size chart is too small to be sure — "
        "reading a number wrong is the most costly error in this task. "
        "Coordinates are fractions of the full image: (0,0) is the top-left "
        "corner and (1,1) the bottom-right. Request several regions in one "
        "turn when you need to compare them. Returns the cropped region as an "
        "image."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "x0": {"type": "number", "description": "Left edge, 0-1."},
            "y0": {"type": "number", "description": "Top edge, 0-1."},
            "x1": {"type": "number", "description": "Right edge, 0-1."},
            "y1": {"type": "number", "description": "Bottom edge, 0-1."},
            "purpose": {
                "type": "string",
                "description": "What you are trying to read in this region.",
            },
        },
        "required": ["x0", "y0", "x1", "y1", "purpose"],
        "additionalProperties": False,
    },
}


_NULLABLE_NUMBER = {"anyOf": [{"type": "number"}, {"type": "null"}]}
_NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}

FINAL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "signal": {"type": "string", "enum": ["BUY", "SELL", "NO_TRADE"]},
        "currency_pair": {"type": "string"},
        "timeframe": {"type": "string"},
        "strategy": {"type": "string"},
        "bias": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "entry_zone": {
            "type": "object",
            "properties": {"low": _NULLABLE_NUMBER, "high": _NULLABLE_NUMBER},
            "required": ["low", "high"],
            "additionalProperties": False,
        },
        "stop_loss": _NULLABLE_NUMBER,
        "take_profit_1": _NULLABLE_NUMBER,
        "take_profit_2": _NULLABLE_NUMBER,
        "risk_reward_ratio": {"type": "string"},
        "confidence_score": {"type": "integer"},
        "key_levels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "price": {"type": "number"},
                    "description": {"type": "string"},
                },
                "required": ["type", "price", "description"],
                "additionalProperties": False,
            },
        },
        "analysis_summary": {"type": "string"},
        "rejection_reason": _NULLABLE_STRING,
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "signal",
        "currency_pair",
        "timeframe",
        "strategy",
        "bias",
        "entry_zone",
        "stop_loss",
        "take_profit_1",
        "take_profit_2",
        "risk_reward_ratio",
        "confidence_score",
        "key_levels",
        "analysis_summary",
        "rejection_reason",
        "warnings",
    ],
    "additionalProperties": False,
}


def _encode_image(image_path: str) -> tuple[str, str]:
    path = Path(image_path)
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8"), media_type


def _crop_region(image_path: str, x0: float, y0: float, x1: float, y1: float) -> str:
    """Crop a fractional region and return it enlarged, as base64 PNG."""
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        width, height = img.size

        # The model supplies fractions; clamp and order them so a malformed
        # box degrades into a valid crop instead of raising.
        x0, x1 = sorted((min(max(x0, 0.0), 1.0), min(max(x1, 0.0), 1.0)))
        y0, y1 = sorted((min(max(y0, 0.0), 1.0), min(max(y1, 0.0), 1.0)))

        box = (
            int(x0 * width),
            int(y0 * height),
            max(int(x1 * width), int(x0 * width) + 1),
            max(int(y1 * height), int(y0 * height) + 1),
        )
        crop = img.crop(box)

    scale = ZOOM_OUTPUT_LONG_EDGE / max(crop.size)
    if scale > 1:
        crop = crop.resize(
            (round(crop.width * scale), round(crop.height * scale)),
            Image.LANCZOS,
        )

    buffer = io.BytesIO()
    crop.save(buffer, format="PNG", optimize=True)
    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")


def _handle_zoom(image_path: str, tool_use) -> dict:
    args = tool_use.input
    try:
        data = _crop_region(
            image_path,
            float(args["x0"]),
            float(args["y0"]),
            float(args["x1"]),
            float(args["y1"]),
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use.id,
            "content": f"Could not crop that region: {exc}. Give x0/y0/x1/y1 as fractions between 0 and 1.",
            "is_error": True,
        }

    return {
        "type": "tool_result",
        "tool_use_id": tool_use.id,
        "content": [
            {"type": "text", "text": f"Enlarged region ({args.get('purpose', '')})."},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": data},
            },
        ],
    }


def _create_message(client, **kwargs):
    """Send one request, with server-side refusal fallback when enabled."""
    if settings.AI_ENABLE_REFUSAL_FALLBACK:
        return client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **kwargs,
        )
    return client.messages.create(**kwargs)


def analyze_chart(
    image_path: str,
    currency_pair: str,
    timeframe: str,
    strategy: str,
) -> tuple[dict, dict]:
    """
    Run the analysis. Returns (run_metadata, final_result).

    `final_result` conforms to FINAL_OUTPUT_SCHEMA. `run_metadata` records how
    the run went — model served, tool calls, token usage — for debugging and
    cost tracking.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    image_data, media_type = _encode_image(image_path)

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        f"Chart: {currency_pair} on the {timeframe} timeframe.\n"
                        f"Strategy: {strategy}.\n\n"
                        "Analyse it and return the JSON."
                    ),
                },
            ],
        }
    ]

    request = {
        "model": settings.AI_CLAUDE_MODEL,
        "max_tokens": settings.AI_CLAUDE_MAX_TOKENS,
        # Stable prefix: tools render before system, so this one breakpoint
        # caches both across every analysis.
        "system": [
            {
                "type": "text",
                "text": build_system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "tools": [ZOOM_TOOL],
        "output_config": {
            "effort": settings.AI_CLAUDE_EFFORT,
            "format": {"type": "json_schema", "schema": FINAL_OUTPUT_SCHEMA},
        },
    }

    zoom_calls = []
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}

    for _ in range(MAX_TOOL_ROUNDS):
        response = _create_message(client, messages=messages, **request)

        for field in usage:
            usage[field] += getattr(response.usage, field, 0) or 0

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            logger.warning("Analysis refused for %s (%s)", currency_pair, category)
            raise AnalysisRefused(f"Request declined by safety classifiers ({category}).")

        if response.stop_reason == "max_tokens":
            raise AnalysisError("Response hit the token limit before finishing.")

        if response.stop_reason != "tool_use":
            final = _parse_final(response)
            metadata = {
                "model": response.model,
                "stop_reason": response.stop_reason,
                "zoom_calls": zoom_calls,
                "usage": usage,
            }
            logger.info(
                "Analysis complete for %s %s: %s (%d zooms, %d output tokens)",
                currency_pair,
                timeframe,
                final.get("signal"),
                len(zoom_calls),
                usage["output_tokens"],
            )
            return metadata, final

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": response.content})
        messages.append(
            {
                "role": "user",
                "content": [_handle_zoom(image_path, block) for block in tool_uses],
            }
        )
        zoom_calls.extend(block.input for block in tool_uses)

    raise AnalysisError(
        f"Model still requesting zooms after {MAX_TOOL_ROUNDS} rounds; giving up."
    )


def _parse_final(response) -> dict:
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise AnalysisError("Model returned no text block.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnalysisError(f"Model output was not valid JSON: {exc}") from exc
