"""Copy existing ProgramCards into Services (comma strings -> JSON lists)."""
from django.db import migrations
from django.utils.text import slugify

ICONS = {"book", "heart", "chart", "shield", "health", "sprout", "leaf", "users"}


def split(text):
    return [part.strip() for part in (text or "").split(",") if part.strip()]


def heading(text, default):
    text = (text or "").strip().rstrip(":").strip()
    return text or default


def forwards(apps, schema_editor):
    ProgramCard = apps.get_model("website", "ProgramCard")
    Service = apps.get_model("website", "Service")
    if Service.objects.exists():
        return
    used = set()
    for position, card in enumerate(ProgramCard.objects.order_by("id"), start=1):
        base = slugify(card.title)[:200] or "service"
        slug, n = base, 2
        while slug in used:
            slug = f"{base}-{n}"
            n += 1
        used.add(slug)
        icon = (card.icon or "").strip().lower()
        Service.objects.create(
            title=card.title,
            slug=slug,
            short_description=(card.description or "")[:160],
            description=card.description or "",
            icon=icon if icon in ICONS else "book",
            activities_heading=heading(card.activities, "Key Activities"),
            activities=split(card.activity_points),
            beneficiaries_heading=heading(card.target, "Target Beneficiaries"),
            beneficiaries=split(card.benefits),
            display_order=position,
            is_published=True,
            show_on_home=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0004_admin_panel_content"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
