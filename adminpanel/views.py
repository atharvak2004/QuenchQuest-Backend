from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import SisUser, User
from authentication.permissions import HasModule, IsAnyStaff
from authentication.sisuser_jwt_auth import SisUserJWTAuthentication
from contact.models import Contact, ContactNote
from dashboard.campaign_stats import with_stats
from dashboard.models import Beneficiary, Campaign, CampaignVolunteer, Donation
from dashboard.serializers import (
    BeneficiarySerializer, CampaignAdminSerializer, CampaignVolunteerSerializer, DonationSerializer,
)
from website.models import (
    DEFAULT_PROJECT_PHASES, DEFAULT_PROJECT_SAFEGUARDS, FAQ, ContentBlock, Leadership,
    MediaAsset, OurImpact, Page, Project, ProjectImage, Service, SiteSettings,
)

from volunteering.models import Attendance

from .csv_export import csv_response
from .images import process_image
from .mixins import (
    ContentViewSet, DuplicateMixin, ImageMixin, PreviewMixin, PublishMixin, ReorderMixin,
    StaffViewSet, bool_param,
)
from .serializers import (
    ContactAdminSerializer, ContactNoteSerializer, ContentBlockAdminSerializer,
    FAQAdminSerializer, GalleryUploadSerializer, IdsSerializer, LeadershipAdminSerializer,
    MediaAssetSerializer, NoteCreateSerializer, OurImpactAdminSerializer, PageAdminSerializer,
    ProjectAdminSerializer, ProjectImageSerializer, StaffResetPasswordSerializer,
    ServiceAdminSerializer, SiteSettingsSerializer, StaffSerializer, VolunteerAdminSerializer,
    VolunteerIdsSerializer,
)


# ---------------------------------------------------------------------------
# Content (module: content)
# ---------------------------------------------------------------------------

class ServiceViewSet(PublishMixin, ReorderMixin, DuplicateMixin, ImageMixin, PreviewMixin, ContentViewSet):
    """Programme areas. Filters: ?is_published= ?show_on_home= ?archived="""

    queryset = Service.objects.all()
    serializer_class = ServiceAdminSerializer
    search_fields = ["title", "short_description", "description"]
    ordering_fields = ["display_order", "title", "created_at", "updated_at"]
    ordering = ["display_order", "id"]
    image_fields = {
        "cover_image": ("cover_image_web", "cover_image_alt"),
        "share_image": (None, None),
    }
    preview_type = "service"
    public_path = "/api/website/services/"

    def filter_list(self, qs):
        show_on_home = bool_param(self.request, "show_on_home")
        if show_on_home is not None:
            qs = qs.filter(show_on_home=show_on_home)
        return qs


class ProjectViewSet(PublishMixin, ReorderMixin, DuplicateMixin, ImageMixin, PreviewMixin, ContentViewSet):
    """Projects. Filters: ?service=<id> ?status= ?is_featured= ?is_published= ?archived=

    Create from the template with ?template=default (fills default phases and safeguards).
    """

    queryset = Project.objects.select_related("service", "updated_by").prefetch_related("gallery")
    serializer_class = ProjectAdminSerializer
    search_fields = ["title", "summary", "location_name"]
    ordering_fields = ["display_order", "featured_order", "title", "start_date", "created_at", "updated_at"]
    ordering = ["display_order", "-created_at"]
    image_fields = {
        "cover_image": ("cover_image_web", "cover_image_alt"),
        "share_image": (None, None),
    }
    preview_type = "project"
    public_path = "/api/website/projects/"

    def get_queryset(self):
        qs = super().get_queryset().select_related("service", "updated_by").prefetch_related("gallery")
        return qs

    def filter_list(self, qs):
        params = self.request.query_params
        if params.get("service"):
            qs = qs.filter(service_id=params["service"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        featured = bool_param(self.request, "is_featured")
        if featured is not None:
            qs = qs.filter(is_featured=featured)
        return qs

    def perform_create(self, serializer):
        extra = {}
        if self.request.query_params.get("template") == "default":
            data = serializer.validated_data
            if not data.get("phases"):
                extra["phases"] = DEFAULT_PROJECT_PHASES
            if not data.get("safeguards"):
                extra["safeguards"] = DEFAULT_PROJECT_SAFEGUARDS
        serializer.save(updated_by=self.request.user, **extra)

    @extend_schema(summary="Default phases and safeguards for a new project", request=None)
    @action(detail=False, methods=["get"])
    def template(self, request):
        return Response({"phases": DEFAULT_PROJECT_PHASES, "safeguards": DEFAULT_PROJECT_SAFEGUARDS})

    def copy_object(self, obj):
        gallery = list(obj.gallery.all())
        original_pk, copy = super().copy_object(obj)
        ProjectImage.objects.bulk_create([
            ProjectImage(project=copy, image=g.image.name, image_web=g.image_web.name,
                         alt=g.alt, display_order=g.display_order)
            for g in gallery
        ])
        return original_pk, copy

    @extend_schema(request=IdsSerializer, summary='Set the home page featured projects, in order: {"ids": [5, 2, 9]}')
    @action(detail=False, methods=["post"], url_path="featured-order")
    def featured_order(self, request):
        serializer = IdsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]
        if len(ids) > Project.MAX_FEATURED:
            raise ValidationError({"ids": f"At most {Project.MAX_FEATURED} featured projects."})
        projects = {p.pk: p for p in Project.objects.filter(pk__in=ids, is_archived=False)}
        if len(projects) != len(set(ids)):
            raise ValidationError({"ids": "Unknown or archived project id."})
        Project.objects.filter(is_featured=True).exclude(pk__in=ids).update(is_featured=False)
        for position, pk in enumerate(ids, start=1):
            project = projects[pk]
            project.is_featured = True
            project.featured_order = position
            project.updated_by = request.user
            project.save()
        return Response({"message": "Featured projects saved.", "ids": ids})

    # --- gallery ----------------------------------------------------------

    @extend_schema(request=GalleryUploadSerializer, responses=ProjectImageSerializer,
                   summary="Add a gallery photo (multipart image + alt, or media_id)")
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser, JSONParser])
    def gallery(self, request, pk=None):
        project = self.get_object()
        payload = GalleryUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        alt = (data.get("alt") or "").strip()
        image = ProjectImage(project=project, display_order=project.gallery.count() + 1)

        if data.get("media_id"):
            asset = MediaAsset.objects.filter(pk=data["media_id"]).first()
            if not asset:
                raise ValidationError({"media_id": "Media item not found."})
            image.image.name = asset.file.name
            image.image_web.name = asset.file_web.name
            alt = alt or asset.alt
        elif data.get("image"):
            processed = process_image(data["image"])
            image.image.save(processed["original"].name, processed["original"], save=False)
            image.image_web.save(processed["web"].name, processed["web"], save=False)
        else:
            raise ValidationError({"image": "Send an image file or a media_id."})

        if not alt:
            raise ValidationError({"alt": "Alt text is required."})
        image.alt = alt
        image.save()
        project.updated_by = request.user
        project.save(update_fields=["updated_by"])
        return Response(ProjectImageSerializer(image, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(request=None, summary="Remove a gallery photo")
    @action(detail=True, methods=["delete"], url_path=r"gallery/(?P<image_id>\d+)")
    def gallery_remove(self, request, pk=None, image_id=None):
        project = self.get_object()
        deleted, _ = ProjectImage.objects.filter(project=project, pk=image_id).delete()
        if not deleted:
            return Response({"Error": "Gallery photo not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"message": "Photo removed."})

    # --- volunteers (needs the volunteers module too) ----------------------

    def _require_volunteers_module(self):
        if not self.request.user.has_module("volunteers"):
            raise PermissionDenied("You need access to volunteers for this.")

    @extend_schema(request=VolunteerIdsSerializer, responses=VolunteerAdminSerializer(many=True),
                   summary="List (GET), add (POST) or remove (DELETE) volunteers on a project")
    @action(detail=True, methods=["get", "post", "delete"])
    def volunteers(self, request, pk=None):
        self._require_volunteers_module()
        project = self.get_object()
        if request.method != "GET":
            payload = VolunteerIdsSerializer(data=request.data)
            payload.is_valid(raise_exception=True)
            people = User.objects.filter(pk__in=payload.validated_data["volunteer_ids"])
            if request.method == "POST":
                project.volunteers.add(*people)
            else:
                project.volunteers.remove(*people)
        data = VolunteerAdminSerializer(project.volunteers.order_by("name"), many=True).data
        return Response(data)

    @extend_schema(
        request=None,
        responses=VolunteerAdminSerializer(many=True),
        summary="Suggest volunteers for a project",
        parameters=[OpenApiParameter("skills", str, description="Comma-separated skills, e.g. teaching,design")],
    )
    @action(detail=True, methods=["get"], url_path="suggested-volunteers")
    def suggested_volunteers(self, request, pk=None):
        """Verified, active volunteers not yet on the project whose skills match ?skills=
        or whose location matches the project's city. Best matches first."""
        self._require_volunteers_module()
        project = self.get_object()
        skills = [s.strip() for s in request.query_params.get("skills", "").split(",") if s.strip()]
        city = project.location_name.split(",")[0].strip() if project.location_name else ""

        match = Q()
        for skill in skills:
            match |= Q(skills__icontains=skill)
        if city:
            match |= Q(location__icontains=city)
        if not match:
            return Response([])

        candidates = (
            User.objects.filter(is_verified=True, is_active=True)
            .filter(match)
            .exclude(pk__in=project.volunteers.values("pk"))
        )

        def score(user):
            text = (user.skills or "").lower()
            points = sum(1 for s in skills if s.lower() in text)
            if city and city.lower() in (user.location or "").lower():
                points += 1
            return points

        ranked = sorted(candidates[:200], key=score, reverse=True)[:50]
        return Response(VolunteerAdminSerializer(ranked, many=True).data)


class LeadershipViewSet(PublishMixin, ReorderMixin, ImageMixin, ContentViewSet):
    queryset = Leadership.objects.all()
    serializer_class = LeadershipAdminSerializer
    search_fields = ["name", "position"]
    ordering_fields = ["display_order", "name", "updated_at"]
    ordering = ["display_order", "id"]
    image_fields = {"image": ("image_web", "image_alt")}


class ImpactViewSet(PublishMixin, ContentViewSet):
    """Impact numbers. The website shows the newest published record by `date`."""

    queryset = OurImpact.objects.all()
    serializer_class = OurImpactAdminSerializer
    ordering_fields = ["date", "updated_at"]
    ordering = ["-date", "-id"]


class FAQViewSet(PublishMixin, ReorderMixin, ContentViewSet):
    queryset = FAQ.objects.all()
    serializer_class = FAQAdminSerializer
    search_fields = ["question", "answer"]
    ordering_fields = ["display_order", "updated_at"]
    ordering = ["display_order", "id"]


class ContentBlockViewSet(PublishMixin, ReorderMixin, ImageMixin, ContentViewSet):
    """Keyed blocks (about.vision, home.hero.headline, ...). Filter: ?prefix=about."""

    queryset = ContentBlock.objects.all()
    serializer_class = ContentBlockAdminSerializer
    search_fields = ["key", "title", "body"]
    ordering_fields = ["key", "display_order", "updated_at"]
    ordering = ["key"]
    image_fields = {"image": ("image_web", "image_alt")}

    def filter_list(self, qs):
        prefix = self.request.query_params.get("prefix")
        return qs.filter(key__startswith=prefix) if prefix else qs


class PageViewSet(PublishMixin, DuplicateMixin, ImageMixin, PreviewMixin, ContentViewSet):
    """Rich-text pages (privacy policy, terms). `body` is HTML."""

    queryset = Page.objects.all()
    serializer_class = PageAdminSerializer
    search_fields = ["title", "body"]
    ordering_fields = ["title", "updated_at"]
    ordering = ["title"]
    image_fields = {"share_image": (None, None)}
    preview_type = "page"
    public_path = "/api/website/pages/"


class SiteSettingsView(APIView):
    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [HasModule]
    module = "content"

    @extend_schema(summary="Get site settings", responses=SiteSettingsSerializer)
    def get(self, request):
        return Response(SiteSettingsSerializer(SiteSettings.load()).data)

    @extend_schema(summary="Update site settings", request=SiteSettingsSerializer, responses=SiteSettingsSerializer)
    def patch(self, request):
        serializer = SiteSettingsSerializer(SiteSettings.load(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)


class MediaAssetViewSet(StaffViewSet):
    """Media library. Upload with multipart `file` + `alt` (+ optional `title`)."""

    queryset = MediaAsset.objects.select_related("uploaded_by")
    serializer_class = MediaAssetSerializer
    search_fields = ["title", "alt"]
    ordering_fields = ["created_at", "size_bytes"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        processed = process_image(serializer.validated_data["file"], field="file")
        asset = serializer.save(
            uploaded_by=self.request.user,
            width=processed["width"],
            height=processed["height"],
            size_bytes=processed["size"],
        )
        asset.file_web.save(processed["web"].name, processed["web"], save=True)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"message": "Deleted. Items already using this image keep their copy."})


# ---------------------------------------------------------------------------
# Inbox (module: inbox)
# ---------------------------------------------------------------------------

class ContactViewSet(StaffViewSet):
    """Contact form messages. Filters: ?status= ?assigned_to=<id>|me|none"""

    module = "inbox"
    http_method_names = ["get", "post", "patch", "head", "options"]
    queryset = Contact.objects.select_related("user", "assigned_to", "project").prefetch_related("notes__author")
    serializer_class = ContactAdminSerializer
    search_fields = ["name", "email", "message", "user__name", "user__email"]
    ordering_fields = ["created_at", "updated_at", "status"]
    ordering = ["-created_at"]

    def create(self, request, *args, **kwargs):
        return Response({"Error": "Messages come from the website contact form."},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("project"):
            qs = qs.filter(project_id=params["project"])
        assigned = params.get("assigned_to")
        if assigned == "me":
            qs = qs.filter(assigned_to=self.request.user)
        elif assigned == "none":
            qs = qs.filter(assigned_to__isnull=True)
        elif assigned:
            qs = qs.filter(assigned_to_id=assigned)
        return qs

    @extend_schema(request=NoteCreateSerializer, responses=ContactNoteSerializer, summary="Add an internal note")
    @action(detail=True, methods=["post"])
    def notes(self, request, pk=None):
        contact = self.get_object()
        payload = NoteCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        note = ContactNote.objects.create(contact=contact, author=request.user, text=payload.validated_data["text"])
        if contact.status == "new":
            contact.status = "in_progress"
            contact.save(update_fields=["status", "updated_at"])
        return Response(ContactNoteSerializer(note).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={(200, "text/csv"): str}, summary="Export messages as CSV (same filters as the list)")
    @action(detail=False, methods=["get"])
    def export(self, request):
        rows = (
            [
                c.id, c.created_at.isoformat(), c.status,
                c.user.name if c.user else c.name,
                c.user.email if c.user else c.email,
                c.user.phone if c.user else c.contact,
                c.address, c.message,
                c.project.title if c.project else "",
                c.assigned_to.username if c.assigned_to else "",
            ]
            for c in self.filter_queryset(self.get_queryset())
        )
        return csv_response(
            "messages",
            ["id", "received", "status", "name", "email", "phone", "address", "message", "project", "assigned_to"],
            rows,
        )


# ---------------------------------------------------------------------------
# Volunteers (module: volunteers)
# ---------------------------------------------------------------------------

class VolunteerViewSet(StaffViewSet):
    """Volunteers. Filters: ?skills= ?location= ?availability= ?gender= ?is_verified= ?is_active=

    DELETE deactivates (the volunteer can't log in); POST /{id}/activate/ undoes it.
    """

    module = "volunteers"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = User.objects.all()
    serializer_class = VolunteerAdminSerializer
    search_fields = ["name", "email", "phone", "volunteer_id", "skills", "location"]
    ordering_fields = ["created_at", "name", "volunteer_id"]
    ordering = ["-id"]

    def create(self, request, *args, **kwargs):
        return Response(
            {"Error": "Use POST /api/dashboard/volunteers/ to create a volunteer."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def get_queryset(self):
        qs = User.objects.prefetch_related("projects").all()
        params = self.request.query_params
        for name in ("skills", "location", "availability"):
            if params.get(name):
                qs = qs.filter(**{f"{name}__icontains": params[name]})
        if params.get("gender"):
            qs = qs.filter(gender__iexact=params["gender"])
        for name in ("is_verified", "is_active"):
            value = bool_param(self.request, name)
            if value is not None:
                qs = qs.filter(**{name: value})
        if params.get("project"):
            qs = qs.filter(projects__id=params["project"])
        return qs

    def destroy(self, request, *args, **kwargs):
        volunteer = self.get_object()
        volunteer.is_active = False
        volunteer.save(update_fields=["is_active"])
        return Response({"message": "Volunteer deactivated.", "is_active": False})

    @extend_schema(request=None, summary="Reactivate a volunteer")
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        volunteer = self.get_object()
        volunteer.is_active = True
        volunteer.save(update_fields=["is_active"])
        return Response({"message": "Volunteer activated.", "is_active": True})

    @extend_schema(request=None, summary="Email a new verification OTP")
    @action(detail=True, methods=["post"], url_path="resend-verification")
    def resend_verification(self, request, pk=None):
        from authentication.views import send_verification_otp

        volunteer = self.get_object()
        if volunteer.is_verified:
            return Response({"Error": "This volunteer is already verified."}, status=status.HTTP_400_BAD_REQUEST)
        send_verification_otp(volunteer)
        return Response({"message": f"Verification OTP sent to {volunteer.email}."})

    @extend_schema(request=None, responses={(200, "text/csv"): str}, summary="Export volunteers as CSV (same filters as the list)")
    @action(detail=False, methods=["get"])
    def export(self, request):
        rows = (
            [
                v.volunteer_id, v.name, v.email, v.phone, v.gender, v.skills, v.location,
                v.availability, "yes" if v.is_verified else "no", "yes" if v.is_active else "no",
                v.created_at.isoformat(),
            ]
            for v in self.filter_queryset(self.get_queryset())
        )
        return csv_response(
            "volunteers",
            ["volunteer_id", "name", "email", "phone", "gender", "skills", "location",
             "availability", "verified", "active", "registered"],
            rows,
        )


# ---------------------------------------------------------------------------
# Staff accounts (module: staff = admins only by default)
# ---------------------------------------------------------------------------

class StaffAccountViewSet(StaffViewSet):
    """Admin, employee and editor accounts. DELETE deactivates; POST /{id}/activate/ undoes it."""

    module = "staff"
    queryset = SisUser.objects.all()
    serializer_class = StaffSerializer
    search_fields = ["username", "email"]
    ordering_fields = ["username", "date_joined", "last_login"]
    ordering = ["username"]

    def get_queryset(self):
        qs = SisUser.objects.all()
        if self.request.query_params.get("role"):
            qs = qs.filter(choice=self.request.query_params["role"])
        active = bool_param(self.request, "is_active")
        if active is not None:
            qs = qs.filter(is_active=active)
        return qs

    def perform_update(self, serializer):
        if serializer.instance == self.request.user and serializer.validated_data.get("choice", "admin") != "admin":
            raise ValidationError({"choice": "You can't remove your own admin role."})
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        staff = self.get_object()
        if staff == request.user:
            return Response({"Error": "You can't deactivate your own account."}, status=status.HTTP_400_BAD_REQUEST)
        staff.is_active = False
        staff.save(update_fields=["is_active"])
        return Response({"message": "Account deactivated.", "is_active": False})

    @extend_schema(request=None, summary="Reactivate a staff account")
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        staff = self.get_object()
        staff.is_active = True
        staff.save(update_fields=["is_active"])
        return Response({"message": "Account activated.", "is_active": True})

    @extend_schema(request=StaffResetPasswordSerializer, summary="Set a new password for a staff member")
    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        staff = self.get_object()
        payload = StaffResetPasswordSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        staff.set_password(payload.validated_data["new_password"])
        staff.failed_login_attempts = 0
        staff.locked_until = None
        staff.save(update_fields=["password", "failed_login_attempts", "locked_until"])
        return Response({"message": "Password reset. Their existing sessions have been logged out."})

    @extend_schema(request=None, summary="Unlock after too many failed logins")
    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        staff = self.get_object()
        staff.failed_login_attempts = 0
        staff.locked_until = None
        staff.save(update_fields=["failed_login_attempts", "locked_until"])
        return Response({"message": "Account unlocked."})


# ---------------------------------------------------------------------------
# Campaigns, beneficiaries, donations (module: campaigns)
# ---------------------------------------------------------------------------

class CampaignAdminViewSet(PublishMixin, ReorderMixin, DuplicateMixin, ImageMixin, PreviewMixin, ContentViewSet):
    """Campaigns. Filters: ?status= ?is_featured= ?service=<id> ?is_published= ?archived="""

    module = "campaigns"
    queryset = Campaign.objects.all()
    serializer_class = CampaignAdminSerializer
    search_fields = ["title", "summary", "description", "location_name"]
    ordering_fields = ["display_order", "start_date", "created_at", "updated_at", "title"]
    ordering = ["display_order", "-created_at"]
    image_fields = {
        "cover_image": ("cover_image_web", "cover_image_alt"),
        "share_image": (None, None),
    }
    preview_type = "campaign"
    public_path = "/api/website/campaigns/"

    def get_queryset(self):
        return with_stats(super().get_queryset()).select_related("service", "project", "updated_by")

    def filter_list(self, qs):
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("service"):
            qs = qs.filter(service_id=params["service"])
        featured = bool_param(self.request, "is_featured")
        if featured is not None:
            qs = qs.filter(is_featured=featured)
        return qs

    def _participants(self):
        campaign = self.get_object()
        return campaign, CampaignVolunteer.objects.filter(campaign=campaign).select_related("volunteer")

    @extend_schema(request=None, responses=CampaignVolunteerSerializer(many=True),
                   summary="Volunteers who joined (paginated)")
    @action(detail=True, methods=["get"])
    def volunteers(self, request, pk=None):
        _, participants = self._participants()
        page = self.paginate_queryset(participants)
        return self.get_paginated_response(CampaignVolunteerSerializer(page, many=True).data)

    @extend_schema(request=None, responses={(200, "text/csv"): str}, summary="Export who joined as CSV")
    @action(detail=True, methods=["get"], url_path="volunteers/export")
    def volunteers_export(self, request, pk=None):
        campaign, participants = self._participants()
        rows = (
            [p.volunteer.volunteer_id, p.volunteer.name, p.volunteer.email, p.volunteer.phone,
             p.volunteer.skills, p.volunteer.location, p.joined_at.isoformat()]
            for p in participants
        )
        return csv_response(
            f"campaign-{campaign.slug}-volunteers",
            ["volunteer_id", "name", "email", "phone", "skills", "location", "joined"],
            rows,
        )


class BeneficiaryAdminViewSet(StaffViewSet):
    module = "campaigns"
    queryset = Beneficiary.objects.select_related("user")
    serializer_class = BeneficiarySerializer
    search_fields = ["need", "location", "user__name", "user__email"]
    ordering_fields = ["created_at", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs


class DonationAdminViewSet(StaffViewSet):
    """Donations. Filters: ?campaign=<id> (or ?campaign=none) ?donor=<id>"""

    module = "campaigns"
    queryset = Donation.objects.select_related("donor", "campaign")
    serializer_class = DonationSerializer
    search_fields = ["donor__name", "donor__email", "campaign__title"]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        campaign = params.get("campaign")
        if campaign == "none":
            qs = qs.filter(campaign__isnull=True)
        elif campaign:
            qs = qs.filter(campaign_id=campaign)
        if params.get("donor"):
            qs = qs.filter(donor_id=params["donor"])
        return qs

    def perform_create(self, serializer):
        if not serializer.validated_data.get("donor"):
            raise ValidationError({"donor": ["This field is required."]})
        serializer.save()


# ---------------------------------------------------------------------------
# Dashboard home (any staff)
# ---------------------------------------------------------------------------

class DashboardHomeView(APIView):
    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [IsAnyStaff]

    @extend_schema(
        summary="Admin dashboard counts and recent activity",
        responses=inline_serializer("DashboardHome", {
            "volunteers": drf_serializers.DictField(),
            "messages": drf_serializers.DictField(),
            "attendance": drf_serializers.DictField(),
            "content": drf_serializers.DictField(),
            "recent_activity": drf_serializers.ListField(child=drf_serializers.DictField()),
        }),
    )
    def get(self, request):
        week_ago = timezone.now() - timedelta(days=7)

        def published(model):
            return model.objects.filter(is_published=True, is_archived=False).count()

        def drafts(model):
            return model.objects.filter(is_published=False, is_archived=False).count()

        activity = []
        for v in User.objects.order_by("-created_at")[:10]:
            activity.append({"type": "volunteer_registered", "id": v.id,
                             "text": f"{v.name} registered", "at": v.created_at})
        for c in Contact.objects.select_related("user").order_by("-created_at")[:10]:
            sender = c.user.name if c.user else (c.name or "Someone")
            activity.append({"type": "message_received", "id": c.id,
                             "text": f"New message from {sender}", "at": c.created_at})
        for model, label in [(Service, "title"), (Project, "title"), (Campaign, "title"), (Page, "title"),
                             (Leadership, "name"), (FAQ, "question"), (ContentBlock, "key")]:
            for item in model.objects.select_related("updated_by").order_by("-updated_at")[:5]:
                if not item.updated_by_id:
                    continue
                activity.append({
                    "type": "content_updated", "model": model._meta.model_name, "id": item.id,
                    "text": f"{item.updated_by.username} updated {model._meta.verbose_name} "
                            f"\"{getattr(item, label)}\"",
                    "at": item.updated_at,
                })
        activity.sort(key=lambda a: a["at"], reverse=True)

        return Response({
            "volunteers": {
                "total": User.objects.count(),
                "new_this_week": User.objects.filter(created_at__gte=week_ago).count(),
                "unverified": User.objects.filter(is_verified=False).count(),
                "inactive": User.objects.filter(is_active=False).count(),
            },
            "messages": {
                "unread": Contact.objects.filter(status="new").count(),
                "open": Contact.objects.filter(status__in=["new", "in_progress"]).count(),
                "assigned_to_me": Contact.objects.filter(
                    assigned_to=request.user, status__in=["new", "in_progress"]
                ).count(),
            },
            "content": {
                "published_projects": published(Project),
                "draft_projects": drafts(Project),
                "published_services": published(Service),
                "draft_services": drafts(Service),
                "published_campaigns": published(Campaign),
                "active_campaigns": Campaign.objects.filter(
                    status="active", is_published=True, is_archived=False
                ).count(),
            },
            "attendance": {
                "pending": Attendance.objects.filter(status="pending").count(),
                "present_today": Attendance.objects.filter(status="approved", date=timezone.localdate()).count(),
            },
            "recent_activity": activity[:15],
        })
