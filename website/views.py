from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import *
from authentication.models import User
from .serializers import *
from drf_spectacular.utils import extend_schema
from authentication.jwt_auth import UserJWTAuthentication
from django.db.models import Q



# Create your views here.


class OurImpactAPI(APIView):
    @extend_schema(summary="Get Impact Statistics",
    description="Retrieve impact metrics and statistics displayed on the website.",
    request=OurImpactSerializer,responses=OurImpactSerializer)

    def get(self, request):

        impacts = OurImpact.objects.all()
        serializer = OurImpactSerializer(impacts,many=True)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
class LatestOurImpactAPI(APIView):
    @extend_schema(summary="Get Latest Impact Data",
    description="Retrieve the most recent impact records and achievements.",
    request=OurImpactSerializer,responses=OurImpactSerializer)

    def get(self, request):
        impact = OurImpact.objects.order_by('-id').first()

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
    @extend_schema(summary="Get Leadership Team",
    description="Retrieve leadership team information displayed on the website.",
    request=LeadershipSerializer,responses=LeadershipSerializer)

    def get(self, request):

        leaders = Leadership.objects.all()
        serializer = LeadershipSerializer(leaders,many=True)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


class ProgramCardAPI(APIView):
    @extend_schema(summary="Get Program Cards",
    description="Retrieve all program cards and related information displayed on the website.",
    request=ProgramCardSerializer,responses=ProgramCardSerializer)

    def get(self, request):

        cards = ProgramCard.objects.all()
        serializer = ProgramCardSerializer(cards,many=True)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


class UserPathSearchAPI(APIView):
    authentication_classes = [UserJWTAuthentication]
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
    authentication_classes = [UserJWTAuthentication]

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

        total_count = users.count()
        # users = users[:limit]       
        print("Total Found:", users.count())
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