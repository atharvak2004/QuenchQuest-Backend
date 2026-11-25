"""Draw a volunteer certificate onto the template image.

Positions are fractions of the template's width/height, so a re-uploaded template
at a different resolution still lines up. DEFAULT_LAYOUT matches the built-in
QuenchQuest design (volunteering/assets/default_certificate.png); a project can
override any part of it with `certificate_layout`.
"""
import copy
import io
import re
import urllib.parse
from functools import lru_cache
from pathlib import Path

import segno
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

DEFAULT_TEMPLATE = Path(__file__).resolve().parent / "assets" / "default_certificate.png"

TEXT_FIELDS = ("name", "project", "date", "certificate_id")

# x / y: anchor point as a fraction of width / height (y is the text baseline).
# size: font height as a fraction of image height. max_width: fraction of width;
# longer text shrinks to fit. qr: top-left corner and side length (fraction of height).
DEFAULT_LAYOUT = {
    "name": {"x": 0.5, "y": 0.447, "size": 0.047, "align": "center", "max_width": 0.5,
             "color": "#12355b", "bold": True},
    "project": {"x": 0.5, "y": 0.585, "size": 0.037, "align": "center", "max_width": 0.5,
                "color": "#1f2937", "bold": True},
    "date": {"x": 0.4968, "y": 0.849, "size": 0.027, "align": "center", "max_width": 0.16,
             "color": "#1f2937", "bold": False},
    "certificate_id": {"x": 0.8405, "y": 0.1185, "size": 0.0205, "align": "left", "max_width": 0.112,
                       "color": "#12355b", "bold": False},
    "qr": {"x": 0.7286, "y": 0.7842, "size": 0.1274},
}

ALIGN_ANCHORS = {"left": "ls", "center": "ms", "right": "rs"}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
ALLOWED_TEMPLATE_FORMATS = {"PNG", "JPEG", "WEBP"}
MIN_TEMPLATE_WIDTH = 800

REGULAR_FONTS = ("georgia.ttf", "DejaVuSerif.ttf", "LiberationSerif-Regular.ttf", "NotoSerif-Regular.ttf", "times.ttf")
BOLD_FONTS = ("georgiab.ttf", "DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf", "NotoSerif-Bold.ttf", "timesbd.ttf")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValidationError({"certificate_layout": f"{name} must be a number between {low} and {high}."})
    return float(value)


def validate_layout(overrides):
    """Check a project's layout overrides and return them cleaned (only known keys)."""
    if overrides in (None, ""):
        return {}
    if not isinstance(overrides, dict):
        raise ValidationError({"certificate_layout": "Must be an object, e.g. {\"name\": {\"y\": 0.45}}."})
    cleaned = {}
    for key, part in overrides.items():
        if key not in DEFAULT_LAYOUT:
            raise ValidationError({"certificate_layout": f"Unknown part '{key}'. Use: {', '.join(DEFAULT_LAYOUT)}."})
        if not isinstance(part, dict):
            raise ValidationError({"certificate_layout": f"'{key}' must be an object."})
        out = {}
        for prop, value in part.items():
            label = f"{key}.{prop}"
            if prop in ("x", "y"):
                out[prop] = _number(value, label, 0, 1)
            elif prop == "size":
                out[prop] = _number(value, label, 0.005, 0.5)
            elif prop == "max_width" and key != "qr":
                out[prop] = _number(value, label, 0.02, 1)
            elif prop == "align" and key != "qr":
                if value not in ALIGN_ANCHORS:
                    raise ValidationError({"certificate_layout": f"{label} must be left, center or right."})
                out[prop] = value
            elif prop == "color" and key != "qr":
                if not isinstance(value, str) or not HEX_COLOR.match(value):
                    raise ValidationError({"certificate_layout": f"{label} must be a colour like #12355b."})
                out[prop] = value
            elif prop == "bold" and key != "qr":
                if not isinstance(value, bool):
                    raise ValidationError({"certificate_layout": f"{label} must be true or false."})
                out[prop] = value
            else:
                raise ValidationError({"certificate_layout": f"Unknown setting '{label}'."})
        cleaned[key] = out
    return cleaned


def effective_layout(overrides=None):
    layout = copy.deepcopy(DEFAULT_LAYOUT)
    for key, part in (overrides or {}).items():
        if key in layout and isinstance(part, dict):
            layout[key].update(part)
    return layout


# ---------------------------------------------------------------------------
# Template upload
# ---------------------------------------------------------------------------

def validate_template(upload):
    """A certificate template: PNG/JPEG/WebP, not huge, wide enough to print."""
    max_mb = settings.MAX_CERTIFICATE_TEMPLATE_MB
    if upload.size > max_mb * 1024 * 1024:
        raise ValidationError({"image": [f"Template must be {max_mb} MB or smaller."]})
    try:
        with Image.open(upload) as probe:
            image_format, width = probe.format, probe.width
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError({"image": ["Upload a PNG, JPEG or WebP image."]})
    if image_format not in ALLOWED_TEMPLATE_FORMATS:
        raise ValidationError({"image": ["Upload a PNG, JPEG or WebP image."]})
    if width < MIN_TEMPLATE_WIDTH:
        raise ValidationError({"image": [f"Template must be at least {MIN_TEMPLATE_WIDTH} px wide."]})
    upload.seek(0)
    return upload


def template_bytes(project):
    """The project's uploaded template, or the built-in one."""
    if project.certificate_template:
        with project.certificate_template.open("rb") as fh:
            return fh.read()
    return DEFAULT_TEMPLATE.read_bytes()


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _font(bold, px):
    configured = settings.CERTIFICATE_FONT_BOLD if bold else settings.CERTIFICATE_FONT
    for name in filter(None, (configured, *(BOLD_FONTS if bold else REGULAR_FONTS))):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default(size=px)


def _fit_font(draw, text, bold, px, max_px_width):
    font = _font(bold, px)
    while px > 8 and draw.textlength(text, font=font) > max_px_width:
        px -= 1
        font = _font(bold, px)
    return font


def verify_url(certificate_id):
    query = urllib.parse.urlencode({"id": certificate_id})
    return f"{settings.CERTIFICATE_VERIFY_URL}?{query}"


def format_date(value):
    return f"{value.day} {value:%B %Y}"


def _qr_image(data, side_px):
    qr = segno.make(data, error="m")
    rows = list(qr.matrix_iter(scale=1, border=1))
    modules = len(rows)
    grid = Image.new("L", (modules, modules), 255)
    pixels = grid.load()
    for y, row in enumerate(rows):
        for x, dark in enumerate(row):
            if dark:
                pixels[x, y] = 0
    # Fill the box exactly; NEAREST keeps every module a hard-edged square block.
    return grid.resize((side_px, side_px), Image.Resampling.NEAREST).convert("RGB")


def render(template, *, name, project, date, certificate_id, layout=None):
    """Return a PIL image of the finished certificate.

    `template` is raw image bytes; `date` a datetime.date; `layout` the project's overrides.
    """
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(template)))
    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
        image = background
    else:
        image = image.convert("RGB")

    width, height = image.size
    draw = ImageDraw.Draw(image)
    spec = effective_layout(layout)
    texts = {"name": name, "project": project, "date": format_date(date), "certificate_id": certificate_id}

    for key in TEXT_FIELDS:
        part = spec[key]
        font = _fit_font(draw, texts[key], part["bold"], max(8, round(part["size"] * height)),
                         part["max_width"] * width)
        draw.text((part["x"] * width, part["y"] * height), texts[key], font=font,
                  fill=part["color"], anchor=ALIGN_ANCHORS[part["align"]])

    qr_spec = spec["qr"]
    side = max(40, round(qr_spec["size"] * height))
    qr = _qr_image(verify_url(certificate_id), side)
    left = round(qr_spec["x"] * width + (side - qr.width) / 2)
    top = round(qr_spec["y"] * height + (side - qr.height) / 2)
    image.paste(qr, (left, top))
    return image


def to_png(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def to_pdf(image):
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "PDF", resolution=150)
    return buffer.getvalue()
