
from rest_framework import serializers
from .models import *



class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "volunteer_id",
            "name",
            "email",
            "gender",
            "phone",
            "skills",
            "location",
            "availability",
            "is_verified",
            "created_at",
        ]

class CreateVolunteerSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField()
    gender = serializers.CharField()
    skills = serializers.CharField()
    location = serializers.CharField(required=False, allow_blank=True)
    availability = serializers.CharField(required=False, allow_blank=True)

class VolunteerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "name",
            "email",
            "phone",
            "gender",
            "skills",
            "location",
            "availability",
            "is_verified"
        ]


from decimal import Decimal

from django.db.models import Sum


def _money(value):
    return f"{(value or Decimal('0')):.2f}"


class CampaignStatsMixin(serializers.Serializer):
    """raised_amount / donor_count / volunteer_count, from with_stats() annotations when present."""

    raised_amount = serializers.SerializerMethodField()
    donor_count = serializers.SerializerMethodField()
    volunteer_count = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()

    def _raised(self, obj):
        value = getattr(obj, "raised_total", None)
        if value is None:
            value = obj.donations.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        return value

    def get_raised_amount(self, obj) -> str:
        return _money(self._raised(obj))

    def get_donor_count(self, obj) -> int:
        value = getattr(obj, "donor_total", None)
        return value if value is not None else obj.donations.values("donor").distinct().count()

    def get_volunteer_count(self, obj) -> int:
        value = getattr(obj, "volunteer_total", None)
        return value if value is not None else obj.participants.count()

    def get_progress_percent(self, obj) -> int | None:
        if not obj.goal_amount:
            return None
        return min(100, int(self._raised(obj) * 100 / obj.goal_amount))


class CampaignAdminSerializer(CampaignStatsMixin, serializers.ModelSerializer):
    service_title = serializers.CharField(source="service.title", read_only=True, default=None)
    project_title = serializers.CharField(source="project.title", read_only=True, default=None)
    project_slug = serializers.CharField(source="project.slug", read_only=True, default=None)
    updated_by_name = serializers.CharField(source="updated_by.username", read_only=True, default=None)

    class Meta:
        model = Campaign
        exclude = ["volunteers"]
        read_only_fields = [
            "created_at", "updated_at", "updated_by", "is_archived", "archived_at",
            "cover_image", "cover_image_web", "share_image",
        ]
        extra_kwargs = {"slug": {"required": False}}

    def validate_goal_amount(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Goal can't be negative.")
        return value

    def validate(self, attrs):
        instance = self.instance
        start = attrs.get("start_date", getattr(instance, "start_date", None))
        end = attrs.get("end_date", getattr(instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date can't be before the start date."})
        return attrs


# The old /api/dashboard/campaigns/ endpoint uses the same shape.
CampaignSerializer = CampaignAdminSerializer


class CampaignPublicSerializer(CampaignStatsMixin, serializers.ModelSerializer):
    service_title = serializers.CharField(source="service.title", read_only=True, default=None)
    service_slug = serializers.CharField(source="service.slug", read_only=True, default=None)
    project_title = serializers.CharField(source="project.title", read_only=True, default=None)
    project_slug = serializers.CharField(source="project.slug", read_only=True, default=None)
    has_joined = serializers.SerializerMethodField()
    my_donation_total = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            "id", "title", "slug", "summary", "description", "status",
            "cover_image", "cover_image_web", "cover_image_alt",
            "start_date", "end_date", "goal_amount", "raised_amount", "progress_percent",
            "donor_count", "volunteer_count",
            "service", "service_title", "service_slug", "project", "project_title", "project_slug",
            "location_name", "allow_volunteers", "is_featured", "display_order",
            "seo_title", "seo_description", "share_image", "is_published", "updated_at",
            "has_joined", "my_donation_total",
        ]

    def _volunteer(self):
        return self.context.get("volunteer")

    def get_has_joined(self, obj) -> bool | None:
        volunteer = self._volunteer()
        if volunteer is None:
            return None
        value = getattr(obj, "joined", None)
        return value if value is not None else obj.participants.filter(volunteer=volunteer).exists()

    def get_my_donation_total(self, obj) -> str | None:
        volunteer = self._volunteer()
        if volunteer is None:
            return None
        value = getattr(obj, "my_total", None)
        if value is None:
            value = obj.donations.filter(donor=volunteer).aggregate(total=Sum("amount"))["total"]
        return _money(value)


class MyCampaignSerializer(CampaignPublicSerializer):
    joined_at = serializers.DateTimeField(read_only=True)

    class Meta(CampaignPublicSerializer.Meta):
        fields = CampaignPublicSerializer.Meta.fields + ["joined_at"]


class CampaignVolunteerSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="volunteer.id", read_only=True)
    volunteer_id = serializers.CharField(source="volunteer.volunteer_id", read_only=True)
    name = serializers.CharField(source="volunteer.name", read_only=True)
    email = serializers.EmailField(source="volunteer.email", read_only=True)
    phone = serializers.CharField(source="volunteer.phone", read_only=True)
    skills = serializers.CharField(source="volunteer.skills", read_only=True)
    location = serializers.CharField(source="volunteer.location", read_only=True)

    class Meta:
        model = CampaignVolunteer
        fields = ["id", "volunteer_id", "name", "email", "phone", "skills", "location", "joined_at"]


class JoinResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    has_joined = serializers.BooleanField()
    volunteer_count = serializers.IntegerField()


class BeneficiarySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = Beneficiary
        fields = [
            "id",
            "user",
            "user_name",
            "user_email",
            "age",
            "need",
            "location",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

class DonationSerializer(serializers.ModelSerializer):
    donor_name = serializers.CharField(source="donor.name", read_only=True)
    campaign_title = serializers.CharField(source="campaign.title", read_only=True, default=None)

    class Meta:
        model = Donation
        fields = [
            "id",
            "donor",
            "donor_name",
            "amount",
            "campaign",
            "campaign_title",
            "created_at"
        ]
        read_only_fields = ["id", "created_at"]
        # Filled automatically from a volunteer token; required for admin/employee (checked in the view).
        extra_kwargs = {"donor": {"required": False}}