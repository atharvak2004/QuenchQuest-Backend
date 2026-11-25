import re

from rest_framework import serializers

from authentication.models import SisUser, User
from contact.models import Contact, ContactNote
from website.models import (
    FAQ, ContentBlock, Leadership, MediaAsset, OurImpact, Page, Project, ProjectImage,
    Service, SiteSettings,
)

AUDIT_READ_ONLY = ["created_at", "updated_at", "updated_by", "is_archived", "archived_at"]


# ---------------------------------------------------------------------------
# JSON list validation
# ---------------------------------------------------------------------------

def validate_text_list(value, max_items=50):
    if not isinstance(value, list):
        raise serializers.ValidationError("Must be a JSON array of strings.")
    if len(value) > max_items:
        raise serializers.ValidationError(f"At most {max_items} items.")
    cleaned = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise serializers.ValidationError("Every item must be a non-empty string.")
        cleaned.append(item.strip())
    return cleaned


def validate_object_list(value, keys, required, max_items=50):
    if not isinstance(value, list):
        raise serializers.ValidationError("Must be a JSON array of objects.")
    if len(value) > max_items:
        raise serializers.ValidationError(f"At most {max_items} items.")
    cleaned = []
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            raise serializers.ValidationError(f"Item {i + 1} must be an object with {', '.join(keys)}.")
        unknown = set(item) - set(keys)
        if unknown:
            raise serializers.ValidationError(f"Item {i + 1} has unknown keys: {', '.join(sorted(unknown))}.")
        row = {}
        for key in keys:
            text = item.get(key, "")
            if not isinstance(text, str):
                raise serializers.ValidationError(f"Item {i + 1}: '{key}' must be text.")
            row[key] = text.strip()
        for key in required:
            if not row[key]:
                raise serializers.ValidationError(f"Item {i + 1}: '{key}' is required.")
        cleaned.append(row)
    return cleaned


class AuditMixin(serializers.Serializer):
    updated_by_name = serializers.CharField(source="updated_by.username", read_only=True, default=None)


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

class ServiceAdminSerializer(AuditMixin, serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY + ["cover_image", "cover_image_web", "share_image"]
        extra_kwargs = {"slug": {"required": False}}

    def validate_activities(self, value):
        return validate_text_list(value)

    def validate_beneficiaries(self, value):
        return validate_text_list(value)


class ProjectImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectImage
        fields = ["id", "image", "image_web", "alt", "display_order", "created_at"]
        read_only_fields = ["id", "image", "image_web", "created_at"]


class ProjectAdminSerializer(AuditMixin, serializers.ModelSerializer):
    gallery = ProjectImageSerializer(many=True, read_only=True)
    service_title = serializers.CharField(source="service.title", read_only=True, default=None)
    volunteer_count = serializers.IntegerField(source="volunteers.count", read_only=True)
    certificate_count = serializers.IntegerField(source="certificates.count", read_only=True)

    class Meta:
        model = Project
        exclude = ["volunteers"]
        read_only_fields = AUDIT_READ_ONLY + [
            "cover_image", "cover_image_web", "share_image", "certificate_template", "certificate_layout",
        ]
        extra_kwargs = {"slug": {"required": False}}

    def validate_activities(self, value):
        return validate_text_list(value)

    def validate_safeguards(self, value):
        return validate_text_list(value)

    def validate_phases(self, value):
        return validate_object_list(value, ["name", "description"], required=["name"])

    def validate_indicators(self, value):
        return validate_object_list(
            value, ["area", "measurement_method", "evidence_source"], required=["area"]
        )

    def validate_latitude(self, value):
        if value is not None and not -90 <= value <= 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        if value is not None and not -180 <= value <= 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value

    def validate(self, attrs):
        instance = self.instance

        def current(name, default=None):
            if name in attrs:
                return attrs[name]
            return getattr(instance, name, default) if instance else default

        start, end = current("start_date"), current("end_date")
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date can't be before the start date."})

        if current("is_featured", False) and not (instance and instance.is_featured):
            featured = Project.objects.filter(is_featured=True, is_archived=False)
            if instance:
                featured = featured.exclude(pk=instance.pk)
            if featured.count() >= Project.MAX_FEATURED:
                raise serializers.ValidationError(
                    {"is_featured": f"Only {Project.MAX_FEATURED} projects can be featured. Unfeature one first."}
                )
        return attrs


class LeadershipAdminSerializer(AuditMixin, serializers.ModelSerializer):
    class Meta:
        model = Leadership
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY + ["image", "image_web"]


class OurImpactAdminSerializer(AuditMixin, serializers.ModelSerializer):
    class Meta:
        model = OurImpact
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY


class FAQAdminSerializer(AuditMixin, serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY


BLOCK_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_.\-]*$")


class ContentBlockAdminSerializer(AuditMixin, serializers.ModelSerializer):
    class Meta:
        model = ContentBlock
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY + ["image", "image_web"]

    def validate_key(self, value):
        value = value.strip().lower()
        if not BLOCK_KEY_RE.match(value):
            raise serializers.ValidationError(
                "Use lowercase letters, numbers, dots, dashes or underscores, e.g. about.vision"
            )
        return value


class PageAdminSerializer(AuditMixin, serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY + ["share_image"]
        extra_kwargs = {"slug": {"required": False}}


class SiteSettingsSerializer(AuditMixin, serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        exclude = ["id", "is_archived", "archived_at", "created_at"]
        read_only_fields = ["updated_at", "updated_by"]

    def validate_get_involved_options(self, value):
        return validate_object_list(value, ["title", "description"], required=["title"])

    def validate_donate_focus_areas(self, value):
        return validate_object_list(value, ["title", "description"], required=["title"])


class MediaAssetSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.username", read_only=True, default=None)

    class Meta:
        model = MediaAsset
        fields = [
            "id", "file", "file_web", "alt", "title", "width", "height", "size_bytes",
            "uploaded_by", "uploaded_by_name", "created_at",
        ]
        read_only_fields = [
            "id", "file_web", "width", "height", "size_bytes", "uploaded_by", "created_at",
        ]

    def validate_alt(self, value):
        if not value.strip():
            raise serializers.ValidationError("Alt text is required.")
        return value.strip()

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:  # the file can't be swapped after upload
            fields["file"].read_only = True
        return fields


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------

class ContactNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.username", read_only=True, default=None)

    class Meta:
        model = ContactNote
        fields = ["id", "text", "author", "author_name", "created_at"]
        read_only_fields = ["id", "author", "created_at"]


class ContactAdminSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_email = serializers.SerializerMethodField()
    sender_phone = serializers.SerializerMethodField()
    is_registered = serializers.SerializerMethodField()
    assigned_to_name = serializers.CharField(source="assigned_to.username", read_only=True, default=None)
    notes = ContactNoteSerializer(many=True, read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True, default=None)
    project_slug = serializers.CharField(source="project.slug", read_only=True, default=None)

    class Meta:
        model = Contact
        fields = [
            "id", "user", "is_registered", "sender_name", "sender_email", "sender_phone",
            "address", "message", "project", "project_title", "project_slug",
            "status", "assigned_to", "assigned_to_name", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "user", "address", "message", "project", "created_at", "updated_at"]

    def get_is_registered(self, obj) -> bool:
        return obj.user_id is not None

    def get_sender_name(self, obj) -> str:
        return obj.user.name if obj.user else obj.name

    def get_sender_email(self, obj) -> str:
        return obj.user.email if obj.user else obj.email

    def get_sender_phone(self, obj) -> str:
        return obj.user.phone if obj.user else obj.contact

    def validate_assigned_to(self, value):
        if value and (not value.is_active or not value.has_module("inbox")):
            raise serializers.ValidationError("That staff member can't access the inbox.")
        return value


# ---------------------------------------------------------------------------
# Volunteers and staff
# ---------------------------------------------------------------------------

class VolunteerAdminSerializer(serializers.ModelSerializer):
    project_ids = serializers.PrimaryKeyRelatedField(source="projects", many=True, read_only=True)
    signs_in_with_google = serializers.SerializerMethodField()

    def get_signs_in_with_google(self, obj) -> bool:
        return bool(obj.google_sub)

    class Meta:
        model = User
        fields = [
            "id", "volunteer_id", "name", "email", "phone", "gender", "skills", "location",
            "availability", "is_verified", "is_active", "created_at", "project_ids", "signs_in_with_google",
        ]
        read_only_fields = ["id", "volunteer_id", "created_at", "project_ids"]


class StaffSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    modules = serializers.SerializerMethodField()
    # Optional: leave it out, or send null / [], to use the role's default modules.
    module_access = serializers.ListField(
        child=serializers.CharField(), required=False, allow_null=True, allow_empty=True,
    )

    class Meta:
        model = SisUser
        fields = [
            "id", "username", "email", "phone", "location", "choice", "module_access", "modules",
            "is_active", "password", "last_login", "date_joined", "locked_until",
            "failed_login_attempts",
        ]
        read_only_fields = [
            "id", "last_login", "date_joined", "locked_until", "failed_login_attempts", "is_active",
        ]

    def get_modules(self, obj) -> list[str]:
        return sorted(obj.modules)

    def validate_module_access(self, value):
        if value is None:  # "no override": the role's default modules apply
            return []
        if any(m not in SisUser.MODULES for m in value):
            raise serializers.ValidationError(f"Use a list from: {', '.join(SisUser.MODULES)}.")
        return sorted(set(value))

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "This field is required."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = SisUser(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        # Passwords are changed via reset-password, not PATCH.
        validated_data.pop("password", None)
        return super().update(instance, validated_data)


class StaffResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(min_length=8)


class IdsSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)


class VolunteerIdsSerializer(serializers.Serializer):
    volunteer_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)


class ImageUploadSerializer(serializers.Serializer):
    """Send either `image` (multipart file) or `media_id` (from the media library)."""

    image = serializers.ImageField(required=False)
    media_id = serializers.IntegerField(required=False)
    field = serializers.CharField(required=False)
    alt = serializers.CharField(required=False, allow_blank=True)


class GalleryUploadSerializer(serializers.Serializer):
    image = serializers.ImageField(required=False)
    media_id = serializers.IntegerField(required=False)
    alt = serializers.CharField(required=False, allow_blank=True)


class NoteCreateSerializer(serializers.Serializer):
    text = serializers.CharField()


class PreviewSerializer(serializers.Serializer):
    token = serializers.CharField()
    expires_in = serializers.IntegerField()
    api_url = serializers.CharField()
