"""Certificates: staff issue them after an event, volunteers download them, anyone verifies them."""
import datetime
import io
import re

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from PIL import Image
from rest_framework import serializers as drf_serializers
from rest_framework import generics, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from adminpanel.mixins import StaffViewSet
from adminpanel.pagination import StandardPagination
from authentication.jwt_auth import UserJWTAuthentication
from authentication.permissions import HasModule, IsVolunteer
from authentication.sisuser_jwt_auth import SisUserJWTAuthentication
from website.models import Project

from . import certificate_service as service
from . import certificates as drawing
from .models import Certificate
from .serializers import (
    CertificateAdminSerializer, CertificateSettingsSerializer, CertificateVerifySerializer,
    EligibleVolunteerSerializer, IssueCertificatesSerializer, IssueResultSerializer, MyCertificateSerializer,
    RevokeSerializer,
)

FILE_TYPES = {"png": "image/png", "pdf": "application/pdf"}
TYPE_PARAM = OpenApiParameter("type", str, enum=["png", "pdf"], description="File type (default png)")
FILE_RESPONSE = {(200, "image/png"): OpenApiResponse(description="PNG (or PDF with ?type=pdf)")}


def file_response(certificate, file_type):
    file_type = (file_type or "png").lower()
    if file_type not in FILE_TYPES:
        raise ValidationError({"type": "Use png or pdf."})
    with certificate.image.open("rb") as fh:
        png = fh.read()
    if file_type == "pdf":
        data = drawing.to_pdf(Image.open(io.BytesIO(png)))
    else:
        data = png
    response = HttpResponse(data, content_type=FILE_TYPES[file_type])
    response["Content-Disposition"] = f'attachment; filename="QuenchQuest-Certificate-{certificate.certificate_id}.{file_type}"'
    return response


# ---------------------------------------------------------------------------
# Staff: per project (module: volunteers)
# ---------------------------------------------------------------------------

class ProjectCertificateView(APIView):
    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [HasModule]
    module = "volunteers"

    def project(self, pk):
        return get_object_or_404(Project, pk=pk)


class CertificateSettingsView(ProjectCertificateView):

    @extend_schema(summary="Certificate settings for a project", responses=CertificateSettingsSerializer)
    def get(self, request, pk):
        return Response(CertificateSettingsSerializer(self.project(pk), context={"request": request}).data)

    @extend_schema(summary="Turn certificates on/off, adjust the layout",
                   request=CertificateSettingsSerializer, responses=CertificateSettingsSerializer)
    def patch(self, request, pk):
        project = self.project(pk)
        serializer = CertificateSettingsSerializer(project, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CertificateTemplateView(ProjectCertificateView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Upload this project's certificate template (multipart `image`)",
        request={"multipart/form-data": {"type": "object", "properties": {"image": {"type": "string", "format": "binary"}}}},
        responses=CertificateSettingsSerializer,
    )
    def post(self, request, pk):
        project = self.project(pk)
        upload = request.FILES.get("image")
        if not upload:
            raise ValidationError({"image": ["Choose a template image."]})
        drawing.validate_template(upload)
        if project.certificate_template:
            project.certificate_template.delete(save=False)
        project.certificate_template.save(upload.name, upload, save=False)
        project.updated_by = request.user
        project.save(update_fields=["certificate_template", "updated_by", "updated_at"])
        return Response(CertificateSettingsSerializer(project, context={"request": request}).data)

    @extend_schema(summary="Go back to the built-in template", request=None, responses=CertificateSettingsSerializer)
    def delete(self, request, pk):
        project = self.project(pk)
        if project.certificate_template:
            project.certificate_template.delete(save=False)
        project.certificate_template = ""
        project.updated_by = request.user
        project.save(update_fields=["certificate_template", "updated_by", "updated_at"])
        return Response(CertificateSettingsSerializer(project, context={"request": request}).data)


class CertificatePreviewView(ProjectCertificateView):

    @extend_schema(
        summary="Preview the certificate with sample text (PNG)",
        parameters=[
            OpenApiParameter("name", str, description='Sample name (default "Volunteer Name")'),
            OpenApiParameter("date", datetime.date, description="Sample date (default today)"),
        ],
        responses=FILE_RESPONSE,
    )
    def get(self, request, pk):
        project = self.project(pk)
        try:
            sample_date = datetime.date.fromisoformat(request.query_params.get("date", ""))
        except ValueError:
            sample_date = timezone.localdate()
        image = drawing.render(
            drawing.template_bytes(project),
            name=(request.query_params.get("name") or "Volunteer Name")[:100],
            project=project.title,
            date=sample_date,
            certificate_id="QQ-SAMP-LE00",
            layout=project.certificate_layout,
        )
        response = HttpResponse(drawing.to_png(image), content_type="image/png")
        response["Cache-Control"] = "no-store"
        return response


class ProjectCertificatesView(ProjectCertificateView):

    @extend_schema(
        summary="Who attended, and who already has a certificate",
        parameters=[OpenApiParameter("min_days", int, description="Approved days needed (default 1)")],
        responses=EligibleVolunteerSerializer(many=True),
    )
    def get(self, request, pk):
        project = self.project(pk)
        try:
            min_days = max(1, int(request.query_params.get("min_days", 1)))
        except ValueError:
            min_days = 1
        issued = {
            c.volunteer_id: c for c in Certificate.objects.filter(project=project).only("volunteer_id", "certificate_id", "status")
        }
        rows = []
        for person in service.attendees(project, min_days):
            certificate = issued.get(person.pk)
            person.certificate_id = certificate.certificate_id if certificate else None
            person.certificate_status = certificate.status if certificate else None
            rows.append(person)
        return Response({
            "certificates_enabled": project.certificates_enabled,
            "attendees": EligibleVolunteerSerializer(rows, many=True).data,
            "issued_count": len(issued),
        })


class IssueCertificatesView(ProjectCertificateView):

    @extend_schema(summary="Issue certificates to volunteers who attended",
                   request=IssueCertificatesSerializer, responses={201: IssueResultSerializer})
    def post(self, request, pk):
        project = self.project(pk)
        if not project.certificates_enabled:
            return Response({"Error": "Turn certificates on for this project first."}, status=status.HTTP_400_BAD_REQUEST)
        if project.is_archived:
            return Response({"Error": "This project is archived."}, status=status.HTTP_400_BAD_REQUEST)

        payload = IssueCertificatesSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        created, skipped = service.issue(
            project,
            date=data.get("date") or project.end_date or timezone.localdate(),
            issued_by=request.user,
            volunteer_ids=data.get("volunteer_ids"),
            min_days=data["min_days"],
            notify=data["notify"],
        )
        return Response(
            {
                "message": f"Issued {len(created)} certificate(s).",
                "issued": CertificateAdminSerializer(created, many=True, context={"request": request}).data,
                "skipped": skipped,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class RegenerateProjectCertificatesView(ProjectCertificateView):

    @extend_schema(
        summary="Re-draw this project's valid certificates with the current template",
        request=None,
        responses=inline_serializer("RegenerateResult", {
            "message": drf_serializers.CharField(), "count": drf_serializers.IntegerField(),
        }),
    )
    def post(self, request, pk):
        project = self.project(pk)
        count = service.redraw(Certificate.objects.filter(project=project, status="valid"))
        return Response({"message": f"Re-drew {count} certificate(s).", "count": count})


# ---------------------------------------------------------------------------
# Staff: all certificates (module: volunteers)
# ---------------------------------------------------------------------------

class CertificateAdminViewSet(StaffViewSet):
    """Issued certificates. Filters: ?project= ?volunteer= ?status=valid|revoked. Search: ID, name, email."""

    module = "volunteers"
    http_method_names = ["get", "post", "head", "options"]
    queryset = Certificate.objects.select_related("volunteer", "issued_by", "project")
    serializer_class = CertificateAdminSerializer
    search_fields = ["certificate_id", "volunteer_name", "volunteer__email", "volunteer__volunteer_id", "project_title"]
    ordering_fields = ["issued_at", "date", "volunteer_name"]
    ordering = ["-issued_at"]

    def create(self, request, *args, **kwargs):
        return Response({"Error": "Issue certificates from the project: POST /api/admin/projects/{id}/certificates/issue/."},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        for name in ("project", "volunteer"):
            if params.get(name):
                qs = qs.filter(**{f"{name}_id": params[name]})
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs

    @extend_schema(request=RevokeSerializer, summary="Revoke (verification then shows it as revoked)")
    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        certificate = self.get_object()
        payload = RevokeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        certificate.status = "revoked"
        certificate.revoked_at = timezone.now()
        certificate.revoke_reason = payload.validated_data.get("reason", "")
        certificate.save(update_fields=["status", "revoked_at", "revoke_reason"])
        return Response(self.get_serializer(certificate).data)

    @extend_schema(request=None, summary="Undo a revoke")
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        certificate = self.get_object()
        certificate.status = "valid"
        certificate.revoked_at = None
        certificate.revoke_reason = ""
        certificate.save(update_fields=["status", "revoked_at", "revoke_reason"])
        return Response(self.get_serializer(certificate).data)

    @extend_schema(request=None, summary="Re-draw with the project's current template (same ID, name and date)")
    @action(detail=True, methods=["post"])
    def regenerate(self, request, pk=None):
        certificate = self.get_object()
        service.redraw(Certificate.objects.filter(pk=certificate.pk))
        certificate.refresh_from_db()
        return Response(self.get_serializer(certificate).data)

    @extend_schema(request=None, parameters=[TYPE_PARAM], responses=FILE_RESPONSE, summary="Download")
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        return file_response(self.get_object(), request.query_params.get("type"))


# ---------------------------------------------------------------------------
# Volunteer
# ---------------------------------------------------------------------------

@extend_schema(summary="My certificates")
class MyCertificatesAPIView(generics.ListAPIView):
    authentication_classes = [UserJWTAuthentication]
    permission_classes = [IsVolunteer]
    pagination_class = StandardPagination
    serializer_class = MyCertificateSerializer

    def get_queryset(self):
        return Certificate.objects.filter(volunteer=self.request.user).select_related("project").order_by("-issued_at")


class CertificateDownloadAPIView(APIView):
    authentication_classes = [UserJWTAuthentication]
    permission_classes = [IsVolunteer]

    @extend_schema(summary="Download my certificate", parameters=[TYPE_PARAM], responses=FILE_RESPONSE)
    def get(self, request, certificate_id):
        certificate = Certificate.objects.filter(
            certificate_id=normalise_id(certificate_id), volunteer=request.user
        ).first()
        if not certificate:
            return Response({"Error": "Certificate not found."}, status=status.HTTP_404_NOT_FOUND)
        if not certificate.is_valid:
            return Response({"Error": "This certificate has been revoked."}, status=status.HTTP_403_FORBIDDEN)
        return file_response(certificate, request.query_params.get("type"))


# ---------------------------------------------------------------------------
# Public verification
# ---------------------------------------------------------------------------

def normalise_id(raw):
    """Accept ' qq-7k3p-9xrm ', 'QQ7K3P9XRM', etc."""
    text = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()
    if re.fullmatch(r"QQ[A-Z0-9]{8}", text):
        return f"QQ-{text[2:6]}-{text[6:]}"
    return (raw or "").strip().upper()


class CertificateVerifyAPIView(APIView):
    """Anyone can check a certificate ID (the QR code on each certificate leads here via the website)."""

    authentication_classes = []
    permission_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "certificate-verify"

    @extend_schema(
        tags=["website"],
        summary="Verify a certificate",
        responses={200: CertificateVerifySerializer, 404: OpenApiResponse(description='{"valid": false, "Error": ...}')},
    )
    def get(self, request, certificate_id):
        certificate = (
            Certificate.objects.select_related("project").filter(certificate_id=normalise_id(certificate_id)).first()
        )
        if not certificate:
            return Response(
                {"valid": False, "Error": "No certificate was found with this ID. Please check it and try again."},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = CertificateVerifySerializer(certificate).data
        data["message"] = (
            "This certificate is genuine and was issued by QuenchQuest Social Foundation."
            if certificate.is_valid
            else "This certificate has been revoked and is no longer valid."
        )
        return Response(data)
