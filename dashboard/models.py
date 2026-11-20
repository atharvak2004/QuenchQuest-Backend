from django.db import models
from authentication.models import User
from website.models import SluggedContentModel


class Campaign(SluggedContentModel):
    """A public campaign (/campaigns/{slug}) that volunteers can join and donations count towards."""

    SLUG_TYPE = "campaign"

    STATUS_CHOICES = [
        ("upcoming", "Upcoming"),
        ("active", "Active"),
        ("completed", "Completed"),
    ]

    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)

    cover_image = models.ImageField(upload_to="campaigns/", blank=True)
    cover_image_web = models.ImageField(upload_to="campaigns/web/", blank=True, editable=False)
    cover_image_alt = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="upcoming")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    goal_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    service = models.ForeignKey(
        "website.Service", null=True, blank=True, on_delete=models.SET_NULL, related_name="campaigns"
    )
    project = models.ForeignKey(
        "website.Project", null=True, blank=True, on_delete=models.SET_NULL, related_name="campaigns"
    )
    location_name = models.CharField(max_length=200, blank=True)

    allow_volunteers = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=False)

    seo_title = models.CharField(max_length=200, blank=True)
    seo_description = models.CharField(max_length=300, blank=True)
    share_image = models.ImageField(upload_to="campaigns/share/", blank=True)

    volunteers = models.ManyToManyField(
        User, through="CampaignVolunteer", blank=True, related_name="joined_campaigns"
    )

    class Meta:
        ordering = ["display_order", "-created_at"]

    @property
    def is_active(self):
        """Kept for old callers; `status` is the source of truth."""
        return self.status == "active"

    def __str__(self):
        return self.title


class CampaignVolunteer(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="participants")
    volunteer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="campaign_participations")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("campaign", "volunteer")
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.volunteer} -> {self.campaign}"


from authentication.models import User

class Beneficiary(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE,null=True,blank=True)
    age = models.IntegerField(null=True, blank=True)
    need = models.CharField(max_length=255, default="Not specified")
    location = models.CharField(max_length=255, default="Unknown")
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("helped", "Helped")
        ],
        default="pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.name if self.user else f"Beneficiary #{self.pk}"

class Donation(models.Model):
    donor = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    campaign = models.ForeignKey(
        Campaign, null=True, blank=True, on_delete=models.SET_NULL, related_name="donations"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.donor.name} - {self.amount}"