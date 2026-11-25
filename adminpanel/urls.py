from django.urls import path
from rest_framework.routers import SimpleRouter

from volunteering import certificate_views as certs
from volunteering.admin_views import AttendanceAdminViewSet, AttendanceCodeViewSet

from . import views

router = SimpleRouter()
# Content
router.register("services", views.ServiceViewSet, basename="admin-services")
router.register("projects", views.ProjectViewSet, basename="admin-projects")
router.register("leadership", views.LeadershipViewSet, basename="admin-leadership")
router.register("impact", views.ImpactViewSet, basename="admin-impact")
router.register("faqs", views.FAQViewSet, basename="admin-faqs")
router.register("content-blocks", views.ContentBlockViewSet, basename="admin-content-blocks")
router.register("pages", views.PageViewSet, basename="admin-pages")
router.register("media", views.MediaAssetViewSet, basename="admin-media")
# Operations
router.register("contacts", views.ContactViewSet, basename="admin-contacts")
router.register("volunteers", views.VolunteerViewSet, basename="admin-volunteers")
router.register("staff", views.StaffAccountViewSet, basename="admin-staff")
router.register("campaigns", views.CampaignAdminViewSet, basename="admin-campaigns")
router.register("beneficiaries", views.BeneficiaryAdminViewSet, basename="admin-beneficiaries")
router.register("donations", views.DonationAdminViewSet, basename="admin-donations")
router.register("attendance", AttendanceAdminViewSet, basename="admin-attendance")
router.register("attendance-codes", AttendanceCodeViewSet, basename="admin-attendance-codes")
router.register("certificates", certs.CertificateAdminViewSet, basename="admin-certificates")

urlpatterns = [
    path("dashboard/", views.DashboardHomeView.as_view(), name="admin-dashboard"),
    path("settings/", views.SiteSettingsView.as_view(), name="admin-settings"),
    # Certificates for one project (listed before the router so they win over /projects/{pk}/...)
    path("projects/<int:pk>/certificate-settings/", certs.CertificateSettingsView.as_view()),
    path("projects/<int:pk>/certificate-template/", certs.CertificateTemplateView.as_view()),
    path("projects/<int:pk>/certificates/", certs.ProjectCertificatesView.as_view()),
    path("projects/<int:pk>/certificates/preview/", certs.CertificatePreviewView.as_view()),
    path("projects/<int:pk>/certificates/issue/", certs.IssueCertificatesView.as_view()),
    path("projects/<int:pk>/certificates/regenerate/", certs.RegenerateProjectCertificatesView.as_view()),
] + router.urls
