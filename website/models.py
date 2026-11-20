from django.db import models
from django.utils import timezone
from django.utils.text import slugify

# Words used as fixed URL segments under /api/website/<resource>/ — never use them as slugs.
RESERVED_SLUGS = {"map", "reorder", "featured", "template", "export"}


# ---------------------------------------------------------------------------
# Shared base classes
# ---------------------------------------------------------------------------

class ContentModel(models.Model):
    """Audit fields + soft delete, shared by every editable content model."""

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_by = models.ForeignKey(
        "authentication.SisUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"updated_at"}
        super().save(*args, **kwargs)


class SlugRedirect(models.Model):
    """Old slug -> current slug, so the website can redirect renamed pages."""

    content_type = models.CharField(max_length=30)
    old_slug = models.SlugField(max_length=220)
    new_slug = models.SlugField(max_length=220)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("content_type", "old_slug")

    def __str__(self):
        return f"{self.content_type}: {self.old_slug} -> {self.new_slug}"


def unique_slug(model, value, exclude_pk=None):
    base = slugify(value)[:200] or "item"
    candidate, n = base, 2
    while True:
        clash = model.objects.filter(slug=candidate)
        if exclude_pk:
            clash = clash.exclude(pk=exclude_pk)
        if candidate not in RESERVED_SLUGS and not clash.exists():
            return candidate
        candidate = f"{base}-{n}"
        n += 1


class SluggedContentModel(ContentModel):
    """Content with a unique URL slug that keeps redirects when the slug changes."""

    SLUG_TYPE = None  # e.g. "service"

    slug = models.SlugField(max_length=220, unique=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        old_slug = None
        if self.pk:
            old_slug = type(self).objects.filter(pk=self.pk).values_list("slug", flat=True).first()

        self.slug = unique_slug(type(self), self.slug or self.title, exclude_pk=self.pk)
        super().save(*args, **kwargs)

        # This slug is live again, so it can't also be a redirect.
        SlugRedirect.objects.filter(content_type=self.SLUG_TYPE, old_slug=self.slug).delete()

        if old_slug and old_slug != self.slug:
            SlugRedirect.objects.filter(
                content_type=self.SLUG_TYPE, new_slug=old_slug
            ).update(new_slug=self.slug)
            SlugRedirect.objects.update_or_create(
                content_type=self.SLUG_TYPE,
                old_slug=old_slug,
                defaults={"new_slug": self.slug},
            )


# ---------------------------------------------------------------------------
# Existing website content
# ---------------------------------------------------------------------------

class OurImpact(ContentModel):

    children_women_supported = models.PositiveIntegerField()
    skill_awareness_programs = models.PositiveIntegerField()
    communities_reached = models.PositiveIntegerField()

    date = models.DateField(help_text="As-of date for these figures")
    is_published = models.BooleanField(default=True)

    def __str__(self):
        return f"Impact - {self.date}"


class Leadership(ContentModel):

    image = models.ImageField(upload_to="leadership/", blank=True)
    image_web = models.ImageField(upload_to="leadership/web/", blank=True, editable=False)
    image_alt = models.CharField(max_length=255, blank=True)

    name = models.CharField(max_length=100)

    position = models.CharField(max_length=100)

    short_description = models.TextField()

    display_order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.name


class ProgramCard(models.Model):
    """Deprecated: replaced by Service. Kept so the old /program-cards/ endpoint still works."""

    icon = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    title = models.CharField(max_length=200)
    description = models.TextField()
    activities = models.CharField(max_length=200,default="Key Activities:")
    activity_points = models.TextField(help_text="Separate values using commas")
    target = models.CharField(max_length=200,default="Target Beneficiaries:")
    benefits = models.TextField(help_text="Separate values using commas")

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# Services (programme areas)
# ---------------------------------------------------------------------------

class Service(SluggedContentModel):
    SLUG_TYPE = "service"

    ICON_CHOICES = [
        (name, name.title())
        for name in ["book", "heart", "chart", "shield", "health", "sprout", "leaf", "users"]
    ]
    LAYOUT_CHOICES = [("wide", "Wide"), ("tall", "Tall")]

    title = models.CharField(max_length=200)
    short_description = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=20, choices=ICON_CHOICES, default="book")

    cover_image = models.ImageField(upload_to="services/", blank=True)
    cover_image_web = models.ImageField(upload_to="services/web/", blank=True, editable=False)
    cover_image_alt = models.CharField(max_length=255, blank=True)

    home_layout = models.CharField(max_length=10, choices=LAYOUT_CHOICES, default="wide")
    activities_heading = models.CharField(max_length=200, default="Key Activities")
    activities = models.JSONField(default=list, blank=True)
    beneficiaries_heading = models.CharField(max_length=200, default="Target Beneficiaries")
    beneficiaries = models.JSONField(default=list, blank=True)

    display_order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=False)
    show_on_home = models.BooleanField(default=True)

    seo_title = models.CharField(max_length=200, blank=True)
    seo_description = models.CharField(max_length=300, blank=True)
    share_image = models.ImageField(upload_to="services/share/", blank=True)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

DEFAULT_PROJECT_PHASES = [
    {"name": "Discover", "description": "Understand the community's needs with local partners."},
    {"name": "Deliver", "description": "Run the planned activities with volunteers and partners."},
    {"name": "Review", "description": "Measure outcomes against the indicators and share what we learned."},
]

DEFAULT_PROJECT_SAFEGUARDS = [
    "Informed consent is taken before any photo, story or data is collected.",
    "All staff and volunteers follow the child and vulnerable-adult safeguarding policy.",
    "Personal data is stored securely and reported only in aggregate.",
]


class Project(SluggedContentModel):
    SLUG_TYPE = "project"

    STATUS_CHOICES = [
        ("concept", "Concept"),
        ("active", "Active"),
        ("completed", "Completed"),
        ("paused", "Paused"),
    ]

    title = models.CharField(max_length=200)
    service = models.ForeignKey(
        Service, null=True, blank=True, on_delete=models.SET_NULL, related_name="projects"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="concept")
    summary = models.CharField(max_length=200, blank=True)

    cover_image = models.ImageField(upload_to="projects/", blank=True)
    cover_image_web = models.ImageField(upload_to="projects/web/", blank=True, editable=False)
    cover_image_alt = models.CharField(max_length=255, blank=True)

    location_name = models.CharField(max_length=200, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    show_on_map = models.BooleanField(default=True)

    challenge = models.TextField(blank=True)
    objective = models.TextField(blank=True)
    participants = models.TextField(blank=True)

    activities = models.JSONField(default=list, blank=True)    # ["...", "..."]
    phases = models.JSONField(default=list, blank=True)        # [{"name", "description"}]
    indicators = models.JSONField(default=list, blank=True)    # [{"area", "measurement_method", "evidence_source"}]
    safeguards = models.JSONField(default=list, blank=True)    # ["...", "..."]

    people_benefited = models.PositiveIntegerField(null=True, blank=True)
    people_benefited_verified = models.BooleanField(default=False)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    is_featured = models.BooleanField(default=False)
    featured_order = models.PositiveIntegerField(default=0)
    display_order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=False)

    seo_title = models.CharField(max_length=200, blank=True)
    seo_description = models.CharField(max_length=300, blank=True)
    share_image = models.ImageField(upload_to="projects/share/", blank=True)

    volunteers = models.ManyToManyField(
        "authentication.User", blank=True, related_name="projects"
    )

    MAX_FEATURED = 3

    class Meta:
        ordering = ["display_order", "-created_at"]

    def __str__(self):
        return self.title


class ProjectImage(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="gallery")
    image = models.ImageField(upload_to="projects/gallery/")
    image_web = models.ImageField(upload_to="projects/gallery/web/", blank=True)
    alt = models.CharField(max_length=255)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "id"]


# ---------------------------------------------------------------------------
# Media library
# ---------------------------------------------------------------------------

class MediaAsset(models.Model):
    file = models.ImageField(upload_to="library/")
    file_web = models.ImageField(upload_to="library/web/", blank=True)
    alt = models.CharField(max_length=255)
    title = models.CharField(max_length=200, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        "authentication.SisUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or self.alt


# ---------------------------------------------------------------------------
# FAQ, settings, content blocks, pages
# ---------------------------------------------------------------------------

class FAQ(ContentModel):
    question = models.CharField(max_length=300)
    answer = models.TextField()
    display_order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["display_order", "id"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class SiteSettings(ContentModel):
    """Single record (pk=1) with contact details, social links and small lists."""

    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)

    linkedin_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)

    footer_tagline = models.CharField(max_length=300, blank=True)

    # [{"title": "...", "description": "..."}]
    get_involved_options = models.JSONField(default=list, blank=True)
    # [{"title": "...", "description": "..."}] - the three Donate page focus areas
    donate_focus_areas = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Site settings"


class ContentBlock(ContentModel):
    """Keyed text/image blocks, e.g. 'about.vision', 'home.hero.headline'."""

    key = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True, help_text="Any extra structured data, e.g. a list of objectives")

    image = models.ImageField(upload_to="blocks/", blank=True)
    image_web = models.ImageField(upload_to="blocks/web/", blank=True, editable=False)
    image_alt = models.CharField(max_length=255, blank=True)

    display_order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class Page(SluggedContentModel):
    """Rich-text pages such as the privacy policy and terms."""

    SLUG_TYPE = "page"

    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, help_text="HTML")
    is_published = models.BooleanField(default=False)

    seo_title = models.CharField(max_length=200, blank=True)
    seo_description = models.CharField(max_length=300, blank=True)
    share_image = models.ImageField(upload_to="pages/share/", blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title
