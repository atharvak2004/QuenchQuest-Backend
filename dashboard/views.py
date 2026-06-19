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
from django.contrib.auth.hashers import make_password
from .serializers import VolunteerUpdateSerializer


# Create your views here.
class VolunteerListCreateAPI(APIView):
    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [IsEmployeeOrAdmin]

    @extend_schema(
        summary="Get Volunteer Data",
        operation_id="volunteer_list",
        description="Retrieve Volunteer statistics.",
        responses=UserListSerializer
    )
    def get(self, request):

        # STATS
        total_volunteers = User.objects.count()
        verified_users = User.objects.filter(is_verified=True).count()
        unverified_users = User.objects.filter(is_verified=False).count()
        male_volunteers = User.objects.filter(gender__iexact="male").count()
        female_volunteers = User.objects.filter(gender__iexact="female").count()

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
                    "male_volunteers": male_volunteers,
                    "female_volunteers": female_volunteers,
                    "new_users_today": new_users_today,
                    "count": volunteers.count(),
                    "volunteers": serializer.data,
                },
                status=status.HTTP_200_OK
            )

        # PAGINATION
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
                "male_volunteers": male_volunteers,
                "female_volunteers": female_volunteers,
                "new_users_today": new_users_today,
                "volunteers": serializer.data,
                "pagination": {
                    "count": paginator.page.paginator.count,
                    "next": paginator.get_next_link(),
                    "previous": paginator.get_previous_link(),
                }
            },
            status=status.HTTP_200_OK
        )

    @extend_schema(
        summary="Create Volunteer",
        operation_id="volunteer_create",
        description="Admin can create volunteer directly.",
        request=CreateVolunteerSerializer,
        responses=UserListSerializer
    )
    def post(self, request):

        name = request.data.get("name")
        email = request.data.get("email")
        phone = request.data.get("phone")
        gender = request.data.get("gender")
        skills = request.data.get("skills")
        location = request.data.get("location")
        availability = request.data.get("availability")

        if not all([name, email, phone, gender, skills]):
            return Response(
                {"Error": "All required fields are mandatory."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(email=email).exists():
            return Response(
                {"Error": "Email already registered."},
                status=status.HTTP_400_BAD_REQUEST
            )

        first_name = name.split()[0].lower()
        password = f"{first_name}{phone[:4]}"

        user = User(
            name=name,
            email=email,
            phone=phone,
            gender=gender,
            skills=skills,
            location=location,
            availability=availability,
            password=make_password(password),
            is_verified=True
        )

        user.save()

        return Response(
            {
                "message": "Volunteer created successfully.",
                "volunteer_id": user.volunteer_id,
                "password": password
            },
            status=status.HTTP_201_CREATED
        )

class VolunteerUpdateAPI(APIView):
    
    @extend_schema(
    summary="Update Volunteer",
    operation_id="volunteer_partial_update",
    description="Admin can partially update volunteer details using volunteer ID (PATCH method).",
    request=VolunteerUpdateSerializer,
    responses=UserListSerializer)
    def patch(self, request, pk):

        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(
                {"Error": "Volunteer not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = VolunteerUpdateSerializer(
            user,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "message": "Volunteer updated successfully.",
                    "volunteer": serializer.data
                },
                status=status.HTTP_200_OK
            )

        return Response(
            {
                "Error": "Invalid data provided.",
                "errors": serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class TotalUsersAPI(APIView):
    @extend_schema(
    summary="Get Users Data",
    description="Retrieve Users statistics.",
    responses=UserListSerializer(many=True))
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


