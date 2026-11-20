from rest_framework import serializers
from .models import *

class OurImpactSerializer(serializers.ModelSerializer):

    class Meta:
        model = OurImpact
        fields = ["id", "children_women_supported", "skill_awareness_programs", "communities_reached", "date"]


class LeadershipSerializer(serializers.ModelSerializer):

    class Meta:
        model = Leadership
        fields = ["id", "name", "position", "short_description", "image", "image_web", "image_alt", "display_order"]


class ProgramCardSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProgramCard
        fields = "__all__"


class UserSearchSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    volunteer_id = serializers.CharField()


class UserSearchResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    returned = serializers.IntegerField()
    results = UserSearchSerializer(many=True)

# ---------------------------------------------------------------------------
# Public serializers for the admin-managed content
# ---------------------------------------------------------------------------

class ServiceRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "title", "slug", "icon"]


class ServicePublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = [
            "id", "title", "slug", "short_description", "description", "icon",
            "cover_image", "cover_image_web", "cover_image_alt", "home_layout",
            "activities_heading", "activities", "beneficiaries_heading", "beneficiaries",
            "display_order", "show_on_home", "seo_title", "seo_description", "share_image",
            "is_published", "updated_at",
        ]


class ProjectImagePublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectImage
        fields = ["id", "image", "image_web", "alt"]


class PeopleBenefitedMixin(serializers.Serializer):
    people_benefited = serializers.SerializerMethodField()

    def get_people_benefited(self, obj) -> int | None:
        # Unverified figures are never published; the website shows "Record pending".
        return obj.people_benefited if obj.people_benefited_verified else None


class ProjectCardPublicSerializer(PeopleBenefitedMixin, serializers.ModelSerializer):
    service = ServiceRefSerializer(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "title", "slug", "service", "status", "summary",
            "cover_image", "cover_image_web", "cover_image_alt", "location_name",
            "is_featured", "featured_order", "people_benefited", "people_benefited_verified",
            "start_date", "end_date",
        ]


class ProjectDetailPublicSerializer(ProjectCardPublicSerializer):
    gallery = ProjectImagePublicSerializer(many=True, read_only=True)

    class Meta(ProjectCardPublicSerializer.Meta):
        fields = ProjectCardPublicSerializer.Meta.fields + [
            "latitude", "longitude", "show_on_map", "challenge", "objective", "participants",
            "activities", "phases", "indicators", "safeguards", "gallery",
            "seo_title", "seo_description", "share_image", "is_published", "updated_at",
        ]


class ProjectMapPinSerializer(serializers.ModelSerializer):
    service = serializers.CharField(source="service.slug", read_only=True, default=None)

    class Meta:
        model = Project
        fields = ["id", "title", "slug", "status", "service", "location_name", "latitude", "longitude"]


class FAQPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ["id", "question", "answer", "display_order"]


class SiteSettingsPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        fields = [
            "contact_email", "contact_phone", "address", "linkedin_url", "instagram_url",
            "facebook_url", "youtube_url", "footer_tagline", "get_involved_options",
            "donate_focus_areas", "updated_at",
        ]


class ContentBlockPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBlock
        fields = ["key", "title", "body", "data", "image", "image_web", "image_alt", "display_order", "updated_at"]


class PageListPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ["title", "slug", "updated_at"]


class PagePublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ["title", "slug", "body", "seo_title", "seo_description", "share_image", "is_published", "updated_at"]


class SiteStatsSerializer(serializers.Serializer):
    volunteers = serializers.IntegerField()
    services = serializers.IntegerField()
    projects = serializers.IntegerField()
    people_benefited = serializers.IntegerField()
    communities_reached = serializers.IntegerField(allow_null=True)
