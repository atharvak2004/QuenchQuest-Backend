"""Validate an uploaded image and build a resized WebP copy for the website."""
import io
import os

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def process_image(upload, field="image"):
    max_mb = settings.MAX_IMAGE_UPLOAD_MB
    if upload.size > max_mb * 1024 * 1024:
        raise ValidationError({field: [f"Image must be {max_mb} MB or smaller."]})

    try:
        probe = Image.open(upload)
        image_format = probe.format
        probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError({field: ["Upload a JPEG, PNG or WebP image."]})
    if image_format not in ALLOWED_FORMATS:
        raise ValidationError({field: ["Upload a JPEG, PNG or WebP image."]})

    upload.seek(0)
    image = ImageOps.exif_transpose(Image.open(upload))
    width, height = image.size
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")

    web = image.copy()
    web.thumbnail((settings.IMAGE_WEB_MAX_PX, settings.IMAGE_WEB_MAX_PX))
    buffer = io.BytesIO()
    web.save(buffer, "WEBP", quality=82)

    upload.seek(0)
    stem = os.path.splitext(os.path.basename(upload.name))[0][:80] or "image"
    return {
        "original": upload,
        "web": ContentFile(buffer.getvalue(), name=f"{stem}.webp"),
        "width": width,
        "height": height,
        "size": upload.size,
    }
