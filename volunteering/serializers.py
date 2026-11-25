from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from website.models import Project, ProjectVolunteer

from . import certificates as drawing
from .models import Attendance, AttendanceCode, Certificate


# ---------------------------------------------------------------------------
# Volunteer side
# ---------------------------------------------------------------------------

class MyProjectSerializer(serializers.ModelSerializer):
    """GET /api/auth/me/projects/ (matches the website's MyProject type)."""

    id = serializers.IntegerField(source="project.id")
    title = serializers.CharField(source="project.title")
    slug = serializers.CharField(source="project.slug")
    status = serializers.CharField(source="project.status")
    summary = serializers.CharField(source="project.summary")
    location_name = serializers.CharField(source="project.location_name")
    latitude = serializers.DecimalField(source="project.latitude", max_digits=9, decimal_places=6, allow_null=True)
    longitude = serializers.DecimalField(source="project.longitude", max_digits=9, decimal_places=6, allow_null=True)
    service_title = serializers.CharField(source="project.service.title", default=None)
    cover_image_web = serializers.ImageField(source="project.cover_image_web", default=None)
    cover_image_alt = serializers.CharField(source="project.cover_image_alt")
    start_date = serializers.DateField(source="project.start_date", allow_null=True)
    end_date = serializers.DateField(source="project.end_date", allow_null=True)
    can_mark_attendance = serializers.SerializerMethodField()
    days_attended = serializers.IntegerField(read_only=True, default=0)
    certificates_enabled = serializers.BooleanField(source="project.certificates_enabled")
    certificate_id = serializers.CharField(read_only=True, default=None)

    class Meta:
        model = ProjectVolunteer
        fields = [
            "id", "title", "slug", "status", "summary", "location_name", "latitude", "longitude",
            "service_title", "cover_image_web", "cover_image_alt", "start_date", "end_date",
            "joined_at", "joined_by", "can_mark_attendance", "days_attended",
            "certificates_enabled", "certificate_id",
        ]

    def get_can_mark_attendance(self, obj) -> bool:
        return obj.project.status in Project.JOINABLE_STATUSES


class AttendanceSerializer(serializers.ModelSerializer):
    """What the volunteer sees (matches the website's Attendance type)."""

    project_title = serializers.CharField(source="project.title", read_only=True)

    class Meta:
        model = Attendance
        fields = ["id", "project", "project_title", "date", "method", "status", "review_note", "created_at"]


class AttendanceSubmitSerializer(serializers.Serializer):
    """Send `code` (JSON) or `photo` (multipart, with optional latitude/longitude)."""

    code = serializers.CharField(required=False, allow_blank=True, max_length=20)
    photo = serializers.ImageField(required=False)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, min_value=-90, max_value=90)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, min_value=-180, max_value=180)

    def validate(self, attrs):
        if not attrs.get("code", "").strip() and not attrs.get("photo"):
            raise serializers.ValidationError({"Error": "Enter the code from the team, or add a photo."})
        if ("latitude" in attrs) != ("longitude" in attrs):
            raise serializers.ValidationError({"Error": "Send both latitude and longitude, or neither."})
        return attrs


class VolunteerSummarySerializer(serializers.Serializer):
    projects = serializers.IntegerField()
    campaigns = serializers.IntegerField()
    attendance_days = serializers.IntegerField()
    pending_attendance = serializers.IntegerField()
    total_donated = serializers.CharField()
    certificates = serializers.IntegerField()


# ---------------------------------------------------------------------------
# Staff side
# ---------------------------------------------------------------------------

class AttendanceAdminSerializer(serializers.ModelSerializer):
    project_title = serializers.CharField(source="project.title", read_only=True)
    volunteer_name = serializers.CharField(source="volunteer.name", read_only=True)
    volunteer_code = serializers.CharField(source="volunteer.volunteer_id", read_only=True)
    volunteer_email = serializers.EmailField(source="volunteer.email", read_only=True)
    code_used = serializers.CharField(source="code.code", read_only=True, default=None)
    reviewed_by_name = serializers.CharField(source="reviewed_by.username", read_only=True, default=None)

    class Meta:
        model = Attendance
        fields = [
            "id", "project", "project_title", "volunteer", "volunteer_name", "volunteer_code",
            "volunteer_email", "date", "method", "status", "code_used", "photo", "latitude", "longitude",
            "reviewed_by", "reviewed_by_name", "reviewed_at", "review_note", "created_at", "updated_at",
        ]
        read_only_fields = fields


class ReviewSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


class BulkReviewSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=500)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


MAX_CODE_HOURS = 72


class AttendanceCodeSerializer(serializers.ModelSerializer):
    """Create with {project, valid_hours (default 12, max 72), note}; the code is generated."""

    project_title = serializers.CharField(source="project.title", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default=None)
    is_valid_now = serializers.BooleanField(read_only=True)
    uses = serializers.IntegerField(source="uses.count", read_only=True)
    valid_hours = serializers.IntegerField(write_only=True, required=False, min_value=1, max_value=MAX_CODE_HOURS)

    class Meta:
        model = AttendanceCode
        fields = [
            "id", "project", "project_title", "code", "note", "valid_from", "valid_until", "valid_hours",
            "is_active", "is_valid_now", "uses", "created_by", "created_by_name", "created_at",
        ]
        read_only_fields = ["id", "code", "is_active", "created_by", "created_at"]
        extra_kwargs = {"valid_from": {"required": False}, "valid_until": {"required": False}}

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:  # project can't move after a code is handed out
            fields["project"].read_only = True
        return fields

    def validate_project(self, project):
        if project.is_archived:
            raise serializers.ValidationError("This project is archived.")
        return project

    def validate(self, attrs):
        instance = self.instance
        valid_from = attrs.get("valid_from") or getattr(instance, "valid_from", None) or timezone.now()
        hours = attrs.pop("valid_hours", None)
        valid_until = attrs.get("valid_until") or getattr(instance, "valid_until", None)
        if hours or not valid_until:
            valid_until = valid_from + timedelta(hours=hours or 12)
        if valid_until <= valid_from:
            raise serializers.ValidationError({"valid_until": "Must be after valid_from."})
        if valid_until - valid_from > timedelta(hours=MAX_CODE_HOURS):
            raise serializers.ValidationError({"valid_until": f"A code can be valid for at most {MAX_CODE_HOURS} hours."})
        attrs["valid_from"], attrs["valid_until"] = valid_from, valid_until
        return attrs


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------

class CertificateLinksMixin(serializers.Serializer):
    verify_url = serializers.SerializerMethodField()

    def get_verify_url(self, obj) -> str:
        return drawing.verify_url(obj.certificate_id)


class MyCertificateSerializer(CertificateLinksMixin, serializers.ModelSerializer):
    """GET /api/auth/me/certificates/"""

    project_slug = serializers.CharField(source="project.slug", read_only=True)
    download_url = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            "certificate_id", "project", "project_title", "project_slug", "volunteer_name", "date",
            "days_attended", "status", "issued_at", "download_url", "pdf_url", "verify_url",
        ]

    def _url(self, obj, kind):
        request = self.context.get("request")
        path = f"/api/certificates/{obj.certificate_id}/download/?type={kind}"
        return request.build_absolute_uri(path) if request else path

    def get_download_url(self, obj) -> str | None:
        return self._url(obj, "png") if obj.is_valid else None

    def get_pdf_url(self, obj) -> str | None:
        return self._url(obj, "pdf") if obj.is_valid else None


class CertificateVerifySerializer(serializers.ModelSerializer):
    """Public answer for the verify page."""

    valid = serializers.BooleanField(source="is_valid")
    project_slug = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            "valid", "status", "certificate_id", "volunteer_name", "project_title", "project_slug",
            "date", "issued_at", "revoked_at",
        ]

    def get_project_slug(self, obj) -> str | None:
        project = obj.project
        return project.slug if project.is_published and not project.is_archived else None


class CertificateAdminSerializer(CertificateLinksMixin, serializers.ModelSerializer):
    volunteer_code = serializers.CharField(source="volunteer.volunteer_id", read_only=True)
    volunteer_email = serializers.EmailField(source="volunteer.email", read_only=True)
    issued_by_name = serializers.CharField(source="issued_by.username", read_only=True, default=None)

    class Meta:
        model = Certificate
        fields = [
            "id", "certificate_id", "project", "project_title", "volunteer", "volunteer_name",
            "volunteer_code", "volunteer_email", "date", "days_attended", "status", "image",
            "revoked_at", "revoke_reason", "issued_by", "issued_by_name", "issued_at", "verify_url",
        ]
        read_only_fields = fields


class IssueCertificatesSerializer(serializers.Serializer):
    date = serializers.DateField(required=False, help_text="Printed date. Default: the project's end date, else today.")
    volunteer_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, allow_empty=False, max_length=1000,
        help_text="Only these volunteers. Default: everyone who attended.",
    )
    min_days = serializers.IntegerField(required=False, min_value=1, default=1)
    notify = serializers.BooleanField(required=False, default=True, help_text="Email each volunteer.")


class RevokeSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300)


class CertificateSettingsSerializer(serializers.Serializer):
    certificates_enabled = serializers.BooleanField(required=False)
    certificate_layout = serializers.JSONField(required=False)
    template_url = serializers.SerializerMethodField()
    uses_default_template = serializers.SerializerMethodField()
    default_layout = serializers.SerializerMethodField()

    def get_template_url(self, project) -> str | None:
        if not project.certificate_template:
            return None
        request = self.context.get("request")
        url = project.certificate_template.url
        return request.build_absolute_uri(url) if request else url

    def get_uses_default_template(self, project) -> bool:
        return not project.certificate_template

    def get_default_layout(self, project) -> dict:
        return drawing.DEFAULT_LAYOUT

    def validate_certificate_layout(self, value):
        return drawing.validate_layout(value)

    def update(self, project, validated_data):
        for field, value in validated_data.items():
            setattr(project, field, value)
        project.save(update_fields=list(validated_data) + ["updated_at"])
        return project


class EligibleVolunteerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    volunteer_id = serializers.CharField()
    name = serializers.CharField()
    email = serializers.EmailField()
    days_attended = serializers.IntegerField(source="days")
    certificate_id = serializers.CharField(allow_null=True)
    certificate_status = serializers.CharField(allow_null=True)


class IssueResultSerializer(serializers.Serializer):
    message = serializers.CharField()
    issued = CertificateAdminSerializer(many=True)
    skipped = serializers.ListField(child=serializers.DictField())
