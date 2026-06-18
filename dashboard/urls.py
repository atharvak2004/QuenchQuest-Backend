from django.urls import path
from .views import *


urlpatterns = [
    path("volunteers/", VolunteerAPI.as_view(), name="volunteers"),
    path("users/", TotalUsersAPIView.as_view(), name="total-users"),

    # path("campaigns/", CampaignAPI.as_view()),
    # path("beneficiaries/", BeneficiaryAPI.as_view()),
    # path("donations/", DonationAPI.as_view()),
]