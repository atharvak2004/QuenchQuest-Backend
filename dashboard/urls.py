from django.urls import path
# from rest_framework.routers import DefaultRouter

from .views import *

# router = DefaultRouter()
# router.register("volunteers", VolunteerAPI, basename="volunteer")

# urlpatterns = router.urls

urlpatterns = [
    path("volunteers/", VolunteerListCreateAPI.as_view()),
    path("volunteers/<int:pk>/", VolunteerUpdateAPI.as_view()),
    path("users/", TotalUsersAPI.as_view(), name="total-users"),

    path("campaigns/", CampaignAPI.as_view()),
    path("beneficiaries/", BeneficiaryAPI.as_view()),
    path("donations/", DonationAPI.as_view()),
]