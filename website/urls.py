from django.urls import path
from rest_framework.routers import SimpleRouter
from dashboard.campaign_views import PublicCampaignViewSet
from volunteering.certificate_views import CertificateVerifyAPIView
from .views import *
from .views import UserPathSearchAPI
from .views import UserQuerySearchAPI
urlpatterns = [
    path("impact/", OurImpactAPI.as_view(), name="impact"),
    path('our-impact/latest/', LatestOurImpactAPI.as_view(), name='latest-our-impact'),
    path("leadership/", LeadershipAPI.as_view(), name="leadership"),
    path("program-cards/",ProgramCardAPI.as_view(),name="program-cards"),
    # path("users/<str:search>/", UserPathSearchAPI.as_view()),
    path("users/", UserQuerySearchAPI.as_view()),
    path("settings/", PublicSiteSettingsAPI.as_view(), name="site-settings"),
    path("stats/", PublicStatsAPI.as_view(), name="site-stats"),
    path("certificates/verify/<str:certificate_id>/", CertificateVerifyAPIView.as_view(), name="certificate-verify"),
]

router = SimpleRouter()
router.register("services", PublicServiceViewSet, basename="services")
router.register("projects", PublicProjectViewSet, basename="projects")
router.register("faqs", PublicFAQViewSet, basename="faqs")
router.register("content-blocks", PublicContentBlockViewSet, basename="content-blocks")
router.register("pages", PublicPageViewSet, basename="pages")
router.register("campaigns", PublicCampaignViewSet, basename="campaigns")
urlpatterns += router.urls