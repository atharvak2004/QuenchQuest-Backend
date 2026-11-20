"""Public campaign pages and the volunteer join/leave endpoints."""
from django.db.models import OuterRef, Subquery
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView

from adminpanel.pagination import StandardPagination
from authentication.jwt_auth import UserJWTAuthentication
from authentication.models import User
from authentication.permissions import IsVolunteer
from website.views import PublicSlugDetailMixin

from .campaign_stats import with_stats
from .models import Campaign, CampaignVolunteer
from .serializers import CampaignPublicSerializer, JoinResponseSerializer, MyCampaignSerializer


class OptionalVolunteerAuthentication(UserJWTAuthentication):
    """Use a volunteer token when it's valid; otherwise treat the request as anonymous.

    Public pages must never fail because the browser still holds an expired token.
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            return None


class OptionalVolunteerAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = OptionalVolunteerAuthentication
    name = "OptionalVolunteerBearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT",
                "description": "Optional volunteer token; adds has_joined and my_donation_total."}


def public_campaigns():
    return Campaign.objects.filter(is_published=True, is_archived=False)


@extend_schema(
    tags=["website"],
    parameters=[
        OpenApiParameter("status", str, description="upcoming | active | completed"),
        OpenApiParameter("featured", bool, description="true = featured campaigns only, in display order"),
        OpenApiParameter("service", str, description="Service slug or id"),
    ],
)
class PublicCampaignViewSet(PublicSlugDetailMixin, viewsets.ReadOnlyModelViewSet):
    """Published campaigns. With a volunteer token, each item also has has_joined and my_donation_total."""

    queryset = Campaign.objects.all()
    serializer_class = CampaignPublicSerializer
    slug_type = "campaign"
    authentication_classes = [OptionalVolunteerAuthentication]

    def volunteer(self):
        user = getattr(self.request, "user", None)
        return user if isinstance(user, User) else None

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["volunteer"] = self.volunteer()
        return context

    def get_queryset(self):
        qs = with_stats(public_campaigns(), self.volunteer()).select_related("service", "project")
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        service = params.get("service")
        if service:
            qs = qs.filter(service_id=service) if service.isdigit() else qs.filter(service__slug=service)
        if params.get("featured") in ("1", "true"):
            qs = qs.filter(is_featured=True)
        return qs.order_by("display_order", "-created_at")


class CampaignJoinAPIView(APIView):
    """POST joins a campaign, DELETE leaves it. Volunteer token required."""

    authentication_classes = [UserJWTAuthentication]
    permission_classes = [IsVolunteer]

    def get_campaign(self, pk):
        return public_campaigns().filter(pk=pk).first()

    def _response(self, campaign, joined, message, code=status.HTTP_200_OK):
        return Response(
            {"message": message, "has_joined": joined, "volunteer_count": campaign.participants.count()},
            status=code,
        )

    @extend_schema(summary="Join a campaign", request=None, responses=JoinResponseSerializer)
    def post(self, request, pk):
        campaign = self.get_campaign(pk)
        if not campaign:
            return Response({"Error": "Campaign not found."}, status=status.HTTP_404_NOT_FOUND)
        if not campaign.allow_volunteers:
            return Response({"Error": "This campaign isn't taking volunteers."}, status=status.HTTP_400_BAD_REQUEST)
        if campaign.status == "completed":
            return Response({"Error": "This campaign has ended."}, status=status.HTTP_400_BAD_REQUEST)

        _, created = CampaignVolunteer.objects.get_or_create(campaign=campaign, volunteer=request.user)
        if created:
            return self._response(campaign, True, "You've joined this campaign.", status.HTTP_201_CREATED)
        return self._response(campaign, True, "You've already joined this campaign.")

    @extend_schema(summary="Leave a campaign", request=None, responses=JoinResponseSerializer)
    def delete(self, request, pk):
        campaign = self.get_campaign(pk)
        if not campaign:
            return Response({"Error": "Campaign not found."}, status=status.HTTP_404_NOT_FOUND)
        CampaignVolunteer.objects.filter(campaign=campaign, volunteer=request.user).delete()
        return self._response(campaign, False, "You've left this campaign.")


@extend_schema(summary="Campaigns I joined, with my donation total for each")
class MyCampaignsAPIView(generics.ListAPIView):
    authentication_classes = [UserJWTAuthentication]
    permission_classes = [IsVolunteer]
    pagination_class = StandardPagination
    serializer_class = MyCampaignSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["volunteer"] = self.request.user
        return context

    def get_queryset(self):
        joined = CampaignVolunteer.objects.filter(campaign=OuterRef("pk"), volunteer=self.request.user)
        qs = public_campaigns().filter(participants__volunteer=self.request.user)
        return (
            with_stats(qs, self.request.user)
            .annotate(joined_at=Subquery(joined.values("joined_at")[:1]))
            .select_related("service", "project")
            .order_by("-joined_at")
        )
