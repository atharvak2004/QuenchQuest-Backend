"""Staff side of attendance: codes to hand out, and approving photo check-ins (module: volunteers)."""
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from adminpanel.csv_export import csv_response
from adminpanel.mixins import StaffViewSet, bool_param

from .models import Attendance, AttendanceCode, new_code
from .serializers import AttendanceAdminSerializer, AttendanceCodeSerializer, BulkReviewSerializer, ReviewSerializer


class AttendanceAdminViewSet(StaffViewSet):
    """Attendance records. Filters: ?status= ?project= ?volunteer= ?method= ?date= ?date_from= ?date_to="""

    module = "volunteers"
    http_method_names = ["get", "post", "delete", "head", "options"]
    queryset = Attendance.objects.select_related("project", "volunteer", "code", "reviewed_by")
    serializer_class = AttendanceAdminSerializer
    search_fields = ["volunteer__name", "volunteer__email", "volunteer__volunteer_id", "project__title"]
    ordering_fields = ["date", "created_at", "status"]
    ordering = ["-date", "-created_at"]

    def create(self, request, *args, **kwargs):
        return Response({"Error": "Volunteers mark attendance from their dashboard."},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        for name in ("status", "method", "date"):
            if params.get(name):
                qs = qs.filter(**{name: params[name]})
        if params.get("project"):
            qs = qs.filter(project_id=params["project"])
        if params.get("volunteer"):
            qs = qs.filter(volunteer_id=params["volunteer"])
        if params.get("date_from"):
            qs = qs.filter(date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(date__lte=params["date_to"])
        return qs

    def _review(self, records, new_status, note):
        now = timezone.now()
        return records.update(status=new_status, reviewed_by=self.request.user, reviewed_at=now,
                              review_note=note or "", updated_at=now)

    def _review_one(self, new_status):
        record = self.get_object()
        payload = ReviewSerializer(data=self.request.data)
        payload.is_valid(raise_exception=True)
        self._review(Attendance.objects.filter(pk=record.pk), new_status, payload.validated_data.get("note"))
        record.refresh_from_db()
        return Response(self.get_serializer(record).data)

    @extend_schema(request=ReviewSerializer, summary="Approve (optional note)")
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._review_one("approved")

    @extend_schema(request=ReviewSerializer, summary="Reject (note is shown to the volunteer)")
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._review_one("rejected")

    @extend_schema(request=BulkReviewSerializer, summary='Approve many pending photos: {"ids": [4, 5]}')
    @action(detail=False, methods=["post"], url_path="bulk-approve")
    def bulk_approve(self, request):
        payload = BulkReviewSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        records = Attendance.objects.filter(pk__in=payload.validated_data["ids"], status="pending")
        count = self._review(records, "approved", payload.validated_data.get("note"))
        return Response({"message": f"Approved {count} record(s).", "approved": count})

    @extend_schema(request=None, responses={(200, "text/csv"): str}, summary="Export as CSV (same filters)")
    @action(detail=False, methods=["get"])
    def export(self, request):
        rows = (
            [a.date.isoformat(), a.project.title, a.volunteer.volunteer_id, a.volunteer.name, a.volunteer.email,
             a.method, a.status, a.code.code if a.code else "", a.latitude or "", a.longitude or "",
             a.reviewed_by.username if a.reviewed_by else "", a.review_note]
            for a in self.filter_queryset(self.get_queryset())
        )
        return csv_response(
            "attendance",
            ["date", "project", "volunteer_id", "name", "email", "method", "status", "code",
             "latitude", "longitude", "reviewed_by", "review_note"],
            rows,
        )


class AttendanceCodeViewSet(StaffViewSet):
    """Codes for a session. Create with {project, valid_hours, note}; DELETE switches a code off.

    Filters: ?project= ?valid=true (usable right now)
    """

    module = "volunteers"
    queryset = AttendanceCode.objects.select_related("project", "created_by").prefetch_related("uses")
    serializer_class = AttendanceCodeSerializer
    search_fields = ["code", "note", "project__title"]
    ordering_fields = ["created_at", "valid_until"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("project"):
            qs = qs.filter(project_id=self.request.query_params["project"])
        valid = bool_param(self.request, "valid")
        if valid is not None:
            now = timezone.now()
            live = Q(is_active=True, valid_from__lte=now, valid_until__gte=now)
            qs = qs.filter(live) if valid else qs.exclude(live)
        return qs

    def perform_create(self, serializer):
        # Pick a code this project hasn't used before (clashes are very unlikely, but cheap to avoid).
        project = serializer.validated_data["project"]
        code = new_code()
        while AttendanceCode.objects.filter(project=project, code=code).exists():
            code = new_code()
        serializer.save(created_by=self.request.user, code=code)

    def destroy(self, request, *args, **kwargs):
        code = self.get_object()
        code.is_active = False
        code.save(update_fields=["is_active"])
        return Response({"message": "Code switched off.", "is_active": False})
