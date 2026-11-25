"""Volunteer-side project endpoints: join/leave, attendance, my projects, my summary."""
import uuid
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Count, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from adminpanel.images import process_image
from adminpanel.pagination import StandardPagination
from authentication.jwt_auth import UserJWTAuthentication
from authentication.permissions import IsVolunteer
from dashboard.models import CampaignVolunteer, Donation
from dashboard.serializers import JoinResponseSerializer
from website.models import Project, ProjectVolunteer

from .models import Attendance, AttendanceCode, Certificate
from .serializers import (
    AttendanceSerializer, AttendanceSubmitSerializer, MyProjectSerializer, VolunteerSummarySerializer,
)

# Wrong attendance codes allowed per volunteer before a 15-minute pause.
MAX_CODE_FAILURES = 5
CODE_FAILURE_WINDOW_SECONDS = 15 * 60


def visible_projects():
    return Project.objects.filter(is_published=True, is_archived=False)


class VolunteerAPIView(APIView):
    authentication_classes = [UserJWTAuthentication]
    permission_classes = [IsVolunteer]

    def error(self, message, code=status.HTTP_400_BAD_REQUEST):
        return Response({"Error": message}, status=code)


class ProjectJoinAPIView(VolunteerAPIView):
    """POST joins a project, DELETE leaves it."""

    def _response(self, project, joined, message, code=status.HTTP_200_OK):
        return Response(
            {"message": message, "has_joined": joined, "volunteer_count": project.memberships.count()},
            status=code,
        )

    @extend_schema(summary="Join a project", request=None, responses=JoinResponseSerializer)
    def post(self, request, pk):
        project = visible_projects().filter(pk=pk).first()
        if not project:
            return self.error("Project not found.", status.HTTP_404_NOT_FOUND)
        if not project.allow_volunteers:
            return self.error("This project isn't taking volunteers.")
        if project.status not in Project.JOINABLE_STATUSES:
            return self.error("This project isn't open to new volunteers right now.")

        _, created = ProjectVolunteer.objects.get_or_create(
            project=project, volunteer=request.user, defaults={"joined_by": "self"}
        )
        if created:
            return self._response(project, True, "You've joined this project.", status.HTTP_201_CREATED)
        return self._response(project, True, "You're already on this project.")

    @extend_schema(summary="Leave a project", request=None, responses=JoinResponseSerializer)
    def delete(self, request, pk):
        project = visible_projects().filter(pk=pk).first()
        if not project:
            return self.error("Project not found.", status.HTTP_404_NOT_FOUND)
        ProjectVolunteer.objects.filter(project=project, volunteer=request.user).delete()
        return self._response(project, False, "You've left this project.")


class ProjectAttendanceAPIView(VolunteerAPIView):
    """Mark today's attendance with a staff code (approved at once) or a photo (pending review)."""

    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(
        summary="Mark attendance for today",
        description=(
            'JSON {"code": "K7P2QX"} is approved at once. Multipart `photo` (+ optional `latitude`, '
            "`longitude`) waits for staff approval. One record per volunteer, project and day; a rejected "
            "one can be sent again."
        ),
        request=AttendanceSubmitSerializer,
        responses={201: AttendanceSerializer},
    )
    def post(self, request, pk):
        project = visible_projects().filter(pk=pk).first()
        if not project:
            return self.error("Project not found.", status.HTTP_404_NOT_FOUND)
        if not ProjectVolunteer.objects.filter(project=project, volunteer=request.user).exists():
            return self.error("Join this project before marking attendance.", status.HTTP_403_FORBIDDEN)
        if project.status not in Project.JOINABLE_STATUSES:
            return self.error("Attendance is closed for this project.")

        payload = AttendanceSubmitSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        today = timezone.localdate()
        record = Attendance.objects.filter(project=project, volunteer=request.user, date=today).first()
        if record and record.status == "approved":
            return self.error("You're already marked present for today.")

        code_text = data.get("code", "").strip().upper()
        if code_text:
            return self._with_code(request, project, record, code_text)
        if record and record.status == "pending":
            return self.error("Your photo for today is waiting for approval.")
        return self._with_photo(request, project, record, data)

    def _with_code(self, request, project, record, code_text):
        fail_key = f"attendance-code-fails:{request.user.pk}"
        if cache.get(fail_key, 0) >= MAX_CODE_FAILURES:
            return self.error("Too many wrong codes. Please try again in 15 minutes.", status.HTTP_429_TOO_MANY_REQUESTS)

        now = timezone.now()
        code = AttendanceCode.objects.filter(
            project=project, code=code_text, is_active=True, valid_from__lte=now, valid_until__gte=now
        ).first()
        if not code:
            cache.add(fail_key, 0, CODE_FAILURE_WINDOW_SECONDS)
            cache.incr(fail_key)
            return self.error("That code isn't valid or has expired. Please check it with the team.")

        cache.delete(fail_key)
        record = record or Attendance(project=project, volunteer=request.user, date=timezone.localdate())
        record.method = "code"
        record.status = "approved"
        record.code = code
        record.reviewed_by, record.reviewed_at, record.review_note = None, None, ""
        created = record.pk is None
        record.save()
        return Response(AttendanceSerializer(record).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def _with_photo(self, request, project, record, data):
        processed = process_image(data["photo"], field="photo")
        record = record or Attendance(project=project, volunteer=request.user, date=timezone.localdate())
        record.method = "photo"
        record.status = "pending"
        record.code = None
        record.latitude = data.get("latitude")
        record.longitude = data.get("longitude")
        record.reviewed_by, record.reviewed_at, record.review_note = None, None, ""
        if record.photo:
            record.photo.delete(save=False)
        # Random name: media is public, so photo URLs must not be guessable.
        record.photo.save(f"{uuid.uuid4().hex}.webp", processed["web"], save=False)
        created = record.pk is None
        record.save()
        return Response(AttendanceSerializer(record).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


def approved_days(project_field="project"):
    """Subquery: approved attendance days for the volunteer on OuterRef(project_field)."""
    days = (
        Attendance.objects.filter(project=OuterRef(project_field), volunteer=OuterRef("volunteer"), status="approved")
        .order_by()
        .values("project")
        .annotate(n=Count("pk"))
        .values("n")[:1]
    )
    return Coalesce(Subquery(days, output_field=IntegerField()), Value(0))


@extend_schema(summary="Projects I'm on", responses=MyProjectSerializer(many=True))
class MyProjectsAPIView(generics.ListAPIView):
    authentication_classes = [UserJWTAuthentication]
    permission_classes = [IsVolunteer]
    pagination_class = StandardPagination
    serializer_class = MyProjectSerializer

    def get_queryset(self):
        return (
            ProjectVolunteer.objects.filter(
                volunteer=self.request.user, project__is_published=True, project__is_archived=False
            )
            .select_related("project", "project__service")
            .annotate(
                days_attended=approved_days(),
                certificate_id=Subquery(
                    Certificate.objects.filter(
                        project=OuterRef("project"), volunteer=OuterRef("volunteer"), status="valid"
                    ).values("certificate_id")[:1]
                ),
            )
            .order_by("-joined_at")
        )


@extend_schema(
    summary="My attendance history",
    parameters=[OpenApiParameter("project", int, description="Only this project")],
)
class MyAttendanceAPIView(generics.ListAPIView):
    authentication_classes = [UserJWTAuthentication]
    permission_classes = [IsVolunteer]
    pagination_class = StandardPagination
    serializer_class = AttendanceSerializer

    def get_queryset(self):
        qs = Attendance.objects.filter(volunteer=self.request.user).select_related("project")
        if self.request.query_params.get("project"):
            qs = qs.filter(project_id=self.request.query_params["project"])
        return qs.order_by("-date", "-created_at")


class MySummaryAPIView(VolunteerAPIView):

    @extend_schema(summary="My dashboard totals", responses=VolunteerSummarySerializer)
    def get(self, request):
        user = request.user
        attendance = Attendance.objects.filter(volunteer=user)
        total = Donation.objects.filter(donor=user).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        return Response({
            "projects": ProjectVolunteer.objects.filter(
                volunteer=user, project__is_published=True, project__is_archived=False
            ).count(),
            "campaigns": CampaignVolunteer.objects.filter(
                volunteer=user, campaign__is_published=True, campaign__is_archived=False
            ).count(),
            "attendance_days": attendance.filter(status="approved").values("date").distinct().count(),
            "pending_attendance": attendance.filter(status="pending").count(),
            "total_donated": f"{total:.2f}",
            "certificates": Certificate.objects.filter(volunteer=user, status="valid").count(),
        })
