from django.urls import path
from .views import *

urlpatterns = [
    path("impact/", OurImpactAPI.as_view(), name="impact"),
    path('our-impact/latest/', LatestOurImpactAPI.as_view(), name='latest-our-impact'),
    path("leadership/", LeadershipAPI.as_view(), name="leadership"),
    path("program-cards/",ProgramCardAPI.as_view(),name="program-cards"),
    ]


