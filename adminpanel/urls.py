from django.urls import path
from rest_framework.routers import SimpleRouter

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

urlpatterns = [
    path("dashboard/", views.DashboardHomeView.as_view(), name="admin-dashboard"),
    path("settings/", views.SiteSettingsView.as_view(), name="admin-settings"),
] + router.urls
