
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime, date
from django.conf import settings
from django.db.models import Sum
from .models import *
from .serializers import *
from authentication.models import *
from contact.models import *
from drf_spectacular.utils import extend_schema
from authentication.jwt_auth import UserJWTAuthentication
from .serializers import UserListSerializer
from django.db.models import Q
from authentication.sisuser_jwt_auth import SisUserJWTAuthentication

from .pagination import VolunteerPagination
from rest_framework.permissions import IsAuthenticated
from authentication.permissions import IsEmployeeOrAdmin

# Create your views here.
class VolunteerAPI(APIView):
    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [IsEmployeeOrAdmin]

    @extend_schema(
        summary="Get Volunteer Data",
        description="Retrieve Volunteer statistics."
    )
    def get(self, request):

        # STATS
        total_volunteers = User.objects.count()
        verified_users = User.objects.filter(is_verified=True).count()
        unverified_users = User.objects.filter(is_verified=False).count()

        today = date.today()
        new_users_today = User.objects.filter(
            created_at__date=today
        ).count()

        recent_users = User.objects.order_by("-id")[:5]
        recent_users_data = [
            {
                "name": u.name,
                "email": u.email,
                "volunteer_id": u.volunteer_id
            }
            for u in recent_users
        ]

        # SEARCH
        search = request.GET.get("search", "")

        volunteers = User.objects.all()

        if search:
            volunteers = volunteers.filter(
                Q(name__istartswith=search) |
                Q(email__istartswith=search) |
                Q(phone__istartswith=search) |
                Q(volunteer_id__istartswith=search) |
                Q(gender__istartswith=search) |
                Q(skills__istartswith=search) |
                Q(location__istartswith=search) |
                Q(availability__istartswith=search)
            ).order_by("-id")

            serializer = UserListSerializer(
                volunteers,
                many=True
            )

            return Response(
                {
                    "total_volunteers": total_volunteers,
                    "verified_users": verified_users,
                    "unverified_users": unverified_users,
                    "new_users_today": new_users_today,
                    "count": volunteers.count(),
                    "volunteers": serializer.data,
                },
                status=status.HTTP_200_OK
            )

        # PAGINATION
        # http://192.168.1.41:8000/api/dashboard/volunteers/?page=6
        volunteers = volunteers.order_by("-id")

        paginator = VolunteerPagination()
        result_page = paginator.paginate_queryset(
            volunteers,
            request
        )

        serializer = UserListSerializer(
            result_page,
            many=True
        )

        return Response(
            {
                "total_volunteers": total_volunteers,
                "verified_users": verified_users,
                "unverified_users": unverified_users,
                "new_users_today": new_users_today,
                # "recent_users": recent_users_data,
                "volunteers": serializer.data,
                "pagination": {
                    "count": paginator.page.paginator.count,
                    "next": paginator.get_next_link(),
                    "previous": paginator.get_previous_link(),
                }
            },
            status=status.HTTP_200_OK
        )
class TotalUsersAPIView(APIView):
    @extend_schema(summary="Get Users Data", description="Retrieve Users statistics.")
    def get(self, request):
        users = User.objects.all()
        serializer = UserListSerializer(users, many=True)

        return Response(
            {
                "total_users": users.count(),
                "users": serializer.data
            },
            status=status.HTTP_200_OK
        )    
      

    
# class TotalUsersAPIView(APIView):
#     def get(self, request):
#         return Response({
#             "total_users": User.objects.count()
#         })


# class CampaignAPI(APIView):

#     authentication_classes = [JWTAuthentication]
#     @extend_schema(
#     summary="Get Campaigns",
#     description="Retrieve all campaigns.",
#     responses=CampaignSerializer)
#     def get(self, request):
#         campaigns = Campaign.objects.all()
#         serializer = CampaignSerializer(campaigns, many=True)
#         return Response(serializer.data)
#     @extend_schema(
#     summary="Create Campaigns",
#     description="create a new campaign.",
#     request=CampaignSerializer,
#     responses=CampaignSerializer)
#     def post(self, request):
#         serializer = CampaignSerializer(data=request.data)

#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=201)
        
#         return Response(serializer.errors, status=400)    
    

# class BeneficiaryAPI(APIView):
#     authentication_classes = [JWTAuthentication]
#     @extend_schema(
#         summary="Get Beneficiaries",
#         description="Retrieve all beneficiaries.",
#         responses=BeneficiarySerializer)
#     def get(self, request):
#         beneficiaries = Beneficiary.objects.select_related('user').all()
#         serializer = BeneficiarySerializer(beneficiaries, many=True)
#         return Response(serializer.data)

#     @extend_schema(
#         summary="Create Beneficiary",
#         description="Create a new beneficiary linked with user.",
#         request=BeneficiarySerializer,
#         responses=BeneficiarySerializer)
#     def post(self, request):
#         data = request.data.copy()
#         # automatically attach logged-in user
#         data['user'] = request.user.id
#         serializer = BeneficiarySerializer(data=data)

#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=201)
#         return Response(serializer.errors, status=400)
    
       
# class DonationAPI(APIView):

#     authentication_classes = [JWTAuthentication]
#     @extend_schema(
#     summary="Get Donations",
#     description="Retrieve all donations.",
#     responses=DonationSerializer)
#     def get(self, request):
#         donations = Donation.objects.all()
#         serializer = DonationSerializer(
#             donations,
#             many=True
#         )
#         return Response(serializer.data)
#     @extend_schema(
#     summary="Create Donations",
#     description="create a new donation.",
#     request=DonationSerializer,
#     responses=DonationSerializer)
#     def post(self, request):
#         serializer = DonationSerializer(data=request.data)

#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=201)

#         return Response(serializer.errors, status=400)    


# class CampaignAPI(APIView):

#     authentication_classes = [JWTAuthentication]
#     @extend_schema(
#     summary="Get Campaigns",
#     description="Retrieve all campaigns.",
#     responses=CampaignSerializer)
#     def get(self, request):
#         campaigns = Campaign.objects.all()
#         serializer = CampaignSerializer(campaigns, many=True)
#         return Response(serializer.data)
#     @extend_schema(
#     summary="Create Campaigns",
#     description="create a new campaign.",
#     request=CampaignSerializer,
#     responses=CampaignSerializer)
#     def post(self, request):
#         serializer = CampaignSerializer(data=request.data)

#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=201)
        
#         return Response(serializer.errors, status=400)    
    

# class BeneficiaryAPI(APIView):
#     authentication_classes = [JWTAuthentication]
#     @extend_schema(
#         summary="Get Beneficiaries",
#         description="Retrieve all beneficiaries.",
#         responses=BeneficiarySerializer)
#     def get(self, request):
#         beneficiaries = Beneficiary.objects.select_related('user').all()
#         serializer = BeneficiarySerializer(beneficiaries, many=True)
#         return Response(serializer.data)

#     @extend_schema(
#         summary="Create Beneficiary",
#         description="Create a new beneficiary linked with user.",
#         request=BeneficiarySerializer,
#         responses=BeneficiarySerializer)
#     def post(self, request):
#         data = request.data.copy()
#         # automatically attach logged-in user
#         data['user'] = request.user.id
#         serializer = BeneficiarySerializer(data=data)

#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=201)
#         return Response(serializer.errors, status=400)
    
       
# class DonationAPI(APIView):

#     authentication_classes = [JWTAuthentication]
#     @extend_schema(
#     summary="Get Donations",
#     description="Retrieve all donations.",
#     responses=DonationSerializer)
#     def get(self, request):
#         donations = Donation.objects.all()
#         serializer = DonationSerializer(
#             donations,
#             many=True
#         )
#         return Response(serializer.data)
#     @extend_schema(
#     summary="Create Donations",
#     description="create a new donation.",
#     request=DonationSerializer,
#     responses=DonationSerializer)
#     def post(self, request):
#         serializer = DonationSerializer(data=request.data)

#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=201)

#         return Response(serializer.errors, status=400)    


