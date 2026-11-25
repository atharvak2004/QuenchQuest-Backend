from django.contrib import admin

from .models import Attendance, AttendanceCode, Certificate


@admin.register(AttendanceCode)
class AttendanceCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "project", "valid_from", "valid_until", "is_active", "created_by")
    list_filter = ("is_active", "project")
    search_fields = ("code", "note", "project__title")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("date", "project", "volunteer", "method", "status", "reviewed_by")
    list_filter = ("status", "method", "project")
    search_fields = ("volunteer__name", "volunteer__email", "volunteer__volunteer_id")
    raw_id_fields = ("volunteer",)
    date_hierarchy = "date"


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("certificate_id", "volunteer_name", "project_title", "date", "status", "issued_at")
    list_filter = ("status", "project")
    search_fields = ("certificate_id", "volunteer_name", "volunteer__email", "project_title")
    raw_id_fields = ("volunteer",)
    readonly_fields = ("certificate_id",)
