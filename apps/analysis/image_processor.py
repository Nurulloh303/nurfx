import io
import logging
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


def sanitize_chart_image(uploaded_file) -> ContentFile:
    """
    Strip EXIF metadata and re-encode image via Pillow to prevent
    image-based RCE / payload injection attacks.

    Re-encodes to PNG, not JPEG: the model has to read price labels and thin
    candle wicks off this image, and JPEG's ringing artifacts land hardest on
    exactly that kind of small high-contrast detail.
    """
    if uploaded_file.size > settings.MAX_CHART_IMAGE_SIZE_BYTES:
        raise ValidationError(
            f"Image exceeds maximum size of {settings.MAX_CHART_IMAGE_SIZE_BYTES // (1024*1024)} MB."
        )

    try:
        raw_bytes = uploaded_file.read()
        img = Image.open(io.BytesIO(raw_bytes))
        width, height = img.size
        if width * height > settings.MAX_CHART_IMAGE_PIXELS:
            raise ValidationError(
                f"Image dimensions too large ({width}x{height}). "
                f"Maximum {settings.MAX_CHART_IMAGE_PIXELS:,} pixels."
            )
        img.verify()
        img = Image.open(io.BytesIO(raw_bytes))
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("Invalid or corrupted image file.") from exc

    if img.format not in settings.ALLOWED_CHART_IMAGE_FORMATS:
        raise ValidationError(
            f"Unsupported image format '{img.format}'. "
            f"Allowed: {', '.join(settings.ALLOWED_CHART_IMAGE_FORMATS)}"
        )

    if img.mode != "RGB":
        img = img.convert("RGB")

    long_edge = max(img.size)
    if long_edge > settings.MAX_CHART_IMAGE_LONG_EDGE:
        scale = settings.MAX_CHART_IMAGE_LONG_EDGE / long_edge
        img = img.resize(
            (round(img.width * scale), round(img.height * scale)),
            Image.LANCZOS,
        )

    output = io.BytesIO()
    img.save(output, format="PNG", optimize=True)
    output.seek(0)

    safe_name = f"{uuid.uuid4().hex}.png"
    logger.info("Sanitized chart image: original=%s, safe=%s", uploaded_file.name, safe_name)
    return ContentFile(output.read(), name=safe_name)
