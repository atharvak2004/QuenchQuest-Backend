"""Step 1 of the campaign upgrade: add slug/status/is_published and fill them for
existing campaigns (slug from title, status from is_active, keep them visible).
0007 then makes slug unique and drops is_active."""
from django.db import migrations, models
from django.utils.text import slugify

RESERVED = {"map", "reorder", "featured", "template", "export"}


def fill(apps, schema_editor):
    Campaign = apps.get_model("dashboard", "Campaign")
    used = set()
    for campaign in Campaign.objects.order_by("id"):
        base = slugify(campaign.title)[:200] or "campaign"
        slug, n = base, 2
        while slug in used or slug in RESERVED:
            slug = f"{base}-{n}"
            n += 1
        used.add(slug)
        campaign.slug = slug
        campaign.status = "active" if campaign.is_active else "completed"
        campaign.is_published = True  # they were already visible to volunteers
        campaign.save(update_fields=["slug", "status", "is_published"])


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0005_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="slug",
            field=models.SlugField(blank=True, default="", max_length=220),
        ),
        migrations.AddField(
            model_name="campaign",
            name="status",
            field=models.CharField(
                choices=[("upcoming", "Upcoming"), ("active", "Active"), ("completed", "Completed")],
                default="upcoming",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="is_published",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
