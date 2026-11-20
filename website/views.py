from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import *
from authentication.models import User
from .serializers import *
from drf_spectacular.utils import extend_schema
from authentication.jwt_auth import UserJWTAuthentication
from authentication.sisuser_jwt_auth import SisUserJWTAuthentication
from authentication.permissions import IsVolunteerOrStaff
from django.db.models import Q



# Create your views here.


class OurImpactAPI(APIView):
    authentication_classes = []
    permission_classes = []
    @extend_schema(summary="Get Impact Statistics",
    description="Retrieve impact metrics and statistics displayed on the website.",
    request=OurImpactSerializer,responses=OurImpactSerializer)

    def get(self, request):

        impacts = OurImpact.objects.filter(is_published=True, is_archived=False).order_by("-date", "-id")
        serializer = OurImpactSerializer(impacts,many=True)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
class LatestOurImpactAPI(APIView):
    authentication_classes = []
    permission_classes = []
    @extend_schema(summary="Get Latest Impact Data",
    description="Retrieve the most recent impact records and achievements.",
    request=OurImpactSerializer,responses=OurImpactSerializer)

    def get(self, request):
        impact = (
            OurImpact.objects.filter(is_published=True, is_archived=False)
            .order_by("-date", "-id")
            .first()
        )

        if not impact:
            return Response(
                {"Error": "No impact data found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = OurImpactSerializer(impact)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
class LeadershipAPI(APIView):
    authentication_classes = []
    permission_classes = []
    @extend_schema(summary="Get Leadership Team",
    description="Retrieve leadership team information displayed on the website.",
    request=LeadershipSerializer,responses=LeadershipSerializer)

    def get(self, request):

        leaders = Leadership.objects.filter(is_published=True, is_archived=False)
        serializer = LeadershipSerializer(leaders, many=True, context={"request": request})

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


class ProgramCardAPI(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(summary="Get Program Cards (deprecated)",
    deprecated=True,
    description="Deprecated: use /api/website/services/. Kept for the old frontend.",
    request=ProgramCardSerializer,responses=ProgramCardSerializer)

    def get(self, request):

        cards = ProgramCard.objects.all()
        serializer = ProgramCardSerializer(cards,many=True)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


class UserPathSearchAPI(APIView):
    authentication_classes = [SisUserJWTAuthentication, UserJWTAuthentication]
    permission_classes = [IsVolunteerOrStaff]
    @extend_schema(
    summary="Search Users by Path Parameter",
    description="Search users by name using a URL path parameter. Supports case-insensitive partial matching and optional limit parameter to control the number of results returned.",
    responses=UserSearchResponseSerializer)
    def get(self, request, search):

        limit = request.GET.get("limit", 10)

        try:
            limit = int(limit)
        except ValueError:
            limit = 10

        users_queryset = User.objects.filter(name__icontains=search)
        total_count = users_queryset.count()
        users = users_queryset[:limit]

        return Response({
            "count": total_count,
            "returned": len(users),
            "results": [
                {
                    "id": u.id,
                    "name": u.name,
                    "email": u.email,
                    "volunteer_id": u.volunteer_id
                }
                for u in users
            ]
        })

class UserQuerySearchAPI(APIView):
    # Returns names/emails, so it must not be public.
    authentication_classes = [SisUserJWTAuthentication, UserJWTAuthentication]
    permission_classes = [IsVolunteerOrStaff]

    @extend_schema(
    summary="Search Users by Query Parameter",
    description="Search users using the search query parameter. Supports case-insensitive partial matching and dynamic limit parameter for controlling the number of returned records.",
    responses=UserSearchResponseSerializer)
    def get(self, request):

        search_query = request.GET.get("search", "")
        # limit = request.GET.get("limit", 10)

        # try:
        #     limit = int(limit)
        # except ValueError:
        #     limit = 10

        users = User.objects.all()

        if search_query:
         users = users.filter(
          Q(name__istartswith=search_query) |
          Q(email__istartswith=search_query) |
          Q(phone__istartswith=search_query) |
          Q(volunteer_id__istartswith=search_query) |
          Q(gender__istartswith=search_query) |
          Q(skills__istartswith=search_query) |
          Q(location__istartswith=search_query) |
          Q(availability__istartswith=search_query)
        )

        users = users.order_by("-id")
        total_count = users.count()
        return Response({
            "count": total_count,
            "returned": len(users),
            "results": [
                {
                    "id": u.id,
                    "name": u.name,
                    "email": u.email,
                    "volunteer_id": u.volunteer_id
                }
                for u in users
            ]
        })


# ---------------------------------------------------------------------------
# Admin-managed content (public, read-only)
# ---------------------------------------------------------------------------

from django.db.models import Sum
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter

from adminpanel.pagination import StandardPagination
from .preview import read_preview_token


class PublicContentMixin:
    """Published, non-archived items only. No auth needed (a stale token is ignored)."""

    authentication_classes = []
    permission_classes = []
    pagination_class = StandardPagination

    def published(self):
        return self.queryset.model.objects.filter(is_published=True, is_archived=False)


class PublicSlugDetailMixin(PublicContentMixin):
    """Detail by slug, with ?preview=<token> for drafts and a 301 for renamed slugs."""

    lookup_field = "slug"
    slug_type = None

    def retrieve(self, request, *args, **kwargs):
        slug = kwargs["slug"]
        token = request.query_params.get("preview")
        if token:
            data = read_preview_token(token)
            obj = None
            if data and data.get("t") == self.slug_type:
                obj = self.queryset.model.objects.filter(pk=data.get("id")).first()
            if not obj:
                raise PermissionDenied("This preview link is invalid or has expired.")
            response = Response(self.get_serializer(obj).data)
            response["Cache-Control"] = "no-store"
            return response

        obj = self.get_queryset().filter(slug=slug).first()
        if obj:
            return Response(self.get_serializer(obj).data)

        redirect = SlugRedirect.objects.filter(content_type=self.slug_type, old_slug=slug).first()
        if redirect and self.get_queryset().filter(slug=redirect.new_slug).exists():
            return Response(
                {"detail": "This page has moved.", "redirect_slug": redirect.new_slug},
                status=status.HTTP_301_MOVED_PERMANENTLY,
            )
        raise NotFound("Not found.")


@extend_schema(tags=["website"])
class PublicServiceViewSet(PublicSlugDetailMixin, viewsets.ReadOnlyModelViewSet):
    """Published services in display order. ?show_on_home=true for the home grid."""

    queryset = Service.objects.all()
    serializer_class = ServicePublicSerializer
    slug_type = "service"

    def get_queryset(self):
        qs = self.published().order_by("display_order", "id")
        if self.request.query_params.get("show_on_home") in ("1", "true"):
            qs = qs.filter(show_on_home=True)
        return qs


@extend_schema(tags=["website"])
class PublicProjectViewSet(PublicSlugDetailMixin, viewsets.ReadOnlyModelViewSet):
    """Published projects. ?service=<slug or id> ?status= ?featured=true ?search="""

    queryset = Project.objects.all()
    slug_type = "project"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["title", "summary", "location_name"]
    ordering_fields = ["display_order", "start_date", "created_at"]

    def get_serializer_class(self):
        return ProjectDetailPublicSerializer if self.action == "retrieve" else ProjectCardPublicSerializer

    def get_queryset(self):
        qs = self.published().select_related("service").prefetch_related("gallery")
        params = self.request.query_params
        service = params.get("service")
        if service:
            qs = qs.filter(service_id=service) if service.isdigit() else qs.filter(service__slug=service)
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("featured") in ("1", "true"):
            return qs.filter(is_featured=True).order_by("featured_order", "id")
        return qs.order_by("display_order", "-created_at")

    @extend_schema(responses=ProjectMapPinSerializer(many=True), summary="Map pins")
    @action(detail=False, methods=["get"], pagination_class=None)
    def map(self, request):
        """Published projects with show_on_map and coordinates. Not paginated."""
        pins = self.published().filter(
            show_on_map=True, latitude__isnull=False, longitude__isnull=False
        ).select_related("service")
        return Response(ProjectMapPinSerializer(pins, many=True).data)


@extend_schema(tags=["website"])
class PublicPageViewSet(PublicSlugDetailMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Page.objects.all()
    slug_type = "page"

    def get_serializer_class(self):
        return PagePublicSerializer if self.action == "retrieve" else PageListPublicSerializer

    def get_queryset(self):
        return self.published().order_by("title")


@extend_schema(tags=["website"])
class PublicFAQViewSet(PublicContentMixin, viewsets.ReadOnlyModelViewSet):
    queryset = FAQ.objects.all()
    serializer_class = FAQPublicSerializer

    def get_queryset(self):
        return self.published().order_by("display_order", "id")


@extend_schema(tags=["website"])
class PublicContentBlockViewSet(PublicContentMixin, viewsets.ReadOnlyModelViewSet):
    """?prefix=about. or ?keys=home.hero.headline,home.hero.subtext"""

    queryset = ContentBlock.objects.all()
    serializer_class = ContentBlockPublicSerializer
    lookup_field = "key"
    lookup_value_regex = r"[a-z0-9][a-z0-9_.\-]*"

    def get_queryset(self):
        qs = self.published().order_by("key")
        params = self.request.query_params
        if params.get("prefix"):
            qs = qs.filter(key__startswith=params["prefix"])
        if params.get("keys"):
            qs = qs.filter(key__in=[k.strip() for k in params["keys"].split(",") if k.strip()])
        return qs


class PublicSiteSettingsAPI(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(tags=["website"], summary="Contact details, social links and footer",
                   responses=SiteSettingsPublicSerializer)
    def get(self, request):
        return Response(SiteSettingsPublicSerializer(SiteSettings.load()).data)


class PublicStatsAPI(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(tags=["website"], summary="Hero stats", responses=SiteStatsSerializer)
    def get(self, request):
        latest = (
            OurImpact.objects.filter(is_published=True, is_archived=False).order_by("-date", "-id").first()
        )
        projects = Project.objects.filter(is_published=True, is_archived=False)
        return Response({
            "volunteers": User.objects.filter(is_verified=True, is_active=True).count(),
            "services": Service.objects.filter(is_published=True, is_archived=False).count(),
            "projects": projects.count(),
            "people_benefited": projects.filter(people_benefited_verified=True)
                                        .aggregate(total=Sum("people_benefited"))["total"] or 0,
            "communities_reached": latest.communities_reached if latest else None,
        })
