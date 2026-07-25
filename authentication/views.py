import random
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime, date
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password

from .models import User
from .serializers import *
from .models import *
from contact.models import *
from drf_spectacular.utils import extend_schema
from .utils import generate_token
from .jwt_auth import *

from rest_framework import generics
from .models import SisUser
from .serializers import SisUserSerializer
from .permissions import IsAdminUserRole
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from .permissions import IsEmployeeOrAdmin, IsSisAdmin
from .permissions import *


import jwt
from datetime import datetime, timedelta
from django.contrib.auth import authenticate
from rest_framework.generics import DestroyAPIView
from .sisuser_jwt_auth import SisUserJWTAuthentication
from .permissions import IsSisAdmin
from django.contrib.auth.hashers import check_password
from rest_framework.generics import DestroyAPIView
from django.http import Http404
from .serializers import ProfileSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .sisuser_jwt_auth import SisUserJWTAuthentication
from .permissions import IsEmployeeOrAdmin  # or allow both roles

from .serializers import ProfileSerializer

from django.core.mail import EmailMultiAlternatives



# REGISTER API
class RegisterAPI(APIView):
    @extend_schema(summary="User Registration",
    description="Create a new user account with the provided registration details.",
    request=RegisterSerializer,
responses=MessageResponseSerializer)
    def post(self, request):

        name = request.data.get("name")
        email = request.data.get("email")
        gender = request.data.get("gender")
        phone = request.data.get("phone")
        skills = request.data.get("skills")
        location = request.data.get("location")
        availability = request.data.get("availability")
        password = request.data.get("password")

        if not name or not email or not gender or not phone or not skills or not password:
          return Response(
        {"Error": "All required fields are mandatory."},
        status=status.HTTP_400_BAD_REQUEST
    )

        if User.objects.filter(email=email).exists():
            return Response(
                {"Error": "Email already registered."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = RegisterSerializer(data=request.data)

        if serializer.is_valid():

            otp = str(random.randint(100000, 999999))

            user = serializer.save(
                password=make_password(password),
                gender=gender,
                phone=phone,
                skills=skills,
                location=location,
                availability=availability
            )

            user.otp = otp
            user.is_verified = False
            user.save()

            send_mail(
                "OTP Verification - QuenchQuest",
                f"""
Hello {user.name},

Thank you for registering with QuenchQuest.

Your OTP for email verification is:{otp}

Please do not share this OTP with anyone.

Regards,
QuenchQuest Team
""",
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False
            )

            return Response(
                {"message": "Registration successful. OTP sent to email."},
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
    

# VERIFY OTP API
class VerifyOTPAPI(APIView):
    @extend_schema(
    summary="Verify OTP",
    description="Verify user OTP.",
    request=VerifyOTPSerializer,
    responses=MessageResponseSerializer)
    def post(self, request):

        email = request.data.get("email")
        otp = request.data.get("otp")

        if not email or not otp:
            return Response(
                {"Error": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)

            if user.otp != otp:
                return Response(
                    {"Error": "Invalid OTP."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user.is_verified = True

            # REMOVE THIS LINE
            # user.otp = None

            user.save()
            send_mail(
        subject="Welcome to QuenchQuest",
        message=f"""
Hello {user.name},

Welcome to QuenchQuest!

Your account has been successfully verified.

Volunteer ID: {user.volunteer_id}

Thank you for joining us and contributing to our mission.

Team QuenchQuest
""",
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[user.email],
        fail_silently=False,
    )
            subject = "🎉 New User Registration"

            from_email = settings.EMAIL_HOST_USER

            to = ["admin@gmail.com"]   # Replace with your admin email

            text_content = f"""
A new user has registered.

Name: {user.name}
Email: {user.email}
Phone: {user.phone}
Location: {user.location}
"""

            html_content = f"""
<!DOCTYPE html>
<html>
<head>
<style>
body {{
    font-family: Arial, sans-serif;
    background:#f5f5f5;
    margin:0;
    padding:30px;
}}

.container {{
    max-width:600px;
    margin:auto;
    background:white;
    border-radius:10px;
    overflow:hidden;
    box-shadow:0 3px 10px rgba(0,0,0,.15);
}}

.header {{
    background:#0d6efd;
    color:white;
    text-align:center;
    padding:20px;
}}

.content {{
    padding:25px;
}}

table {{
    width:100%;
    border-collapse:collapse;
}}

td {{
    padding:12px;
    border-bottom:1px solid #eee;
}}

.label {{
    font-weight:bold;
}}

.footer {{
    background:#f8f9fa;
    text-align:center;
    color:#777;
    padding:15px;
    font-size:13px;
}}
</style>
</head>

<body>

<div class="container">

<div class="header">
<h2>🎉 New User Registration</h2>
</div>

<div class="content">

<p style="color:green;font-size:18px;">
A new user has successfully registered.
</p>

<table>

<tr>
<td class="label">👤 Name</td>
<td>{user.name}</td>
</tr>

<tr>
<td class="label">📧 Email</td>
<td>{user.email}</td>
</tr>

<tr>
<td class="label">📱 Phone</td>
<td>{user.phone}</td>
</tr>

<tr>
<td class="label">📍 Location</td>
<td>{user.location}</td>
</tr>

</table>

</div>

<div class="footer">
This email was automatically generated by QuenchQuest.
</div>

</div>

</body>
</html>
"""

            admin_email = EmailMultiAlternatives(
                subject,
                text_content,
                from_email,
                to,
            )

            admin_email.attach_alternative(html_content, "text/html")
            admin_email.send()
                    

            return Response(
                {"message": "OTP verified successfully."},
                status=status.HTTP_200_OK
            )

        except User.DoesNotExist:
            return Response(
                {"Error": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )

# LOGIN API
class LoginAPI(APIView):
    @extend_schema(
    summary="User Login",
    description="Authenticate user.",
    request=LoginSerializer,
    responses=RegisterSerializer)

    def post(self, request):

        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"Error": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)

            if not check_password(password, user.password):
                return Response(
                    {
                        "Error": "The email address or password you entered is incorrect."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not user.is_verified:
                return Response(
                    {"Error": "Please verify your email first."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            token = generate_token(user)
            return Response(
                {
                    "message": "Login successful.",
                    "user": {
                         "name": user.name,
                         "email": user.email,
                         "phone": user.phone,
                         "gender": user.gender,
                         "skills": user.skills,
                         "location": user.location,
                         "availability": user.availability,
        },
                    "token": token,
                    
                },
                status=status.HTTP_200_OK
            )

        except User.DoesNotExist:
            return Response(
                {"Error": "User not found."},
                status=status.HTTP_400_BAD_REQUEST
            )
        

# FORGOT PASSWORD API
class ForgotPasswordAPI(APIView):
    @extend_schema(
    summary="Forgot Password",
    request=ForgotPasswordSerializer,
    responses=MessageResponseSerializer
)

    def post(self, request):

        email = request.data.get("email")

        if not email:
            return Response(
                {"Error": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)

            otp = str(random.randint(100000, 999999))

            user.otp = otp
            user.save()

            send_mail(
                "Password Reset OTP - QuenchQuest",
                f"""
Hello {user.name},

Your OTP for password reset is:

{otp}

Regards,
QuenchQuest Team
""",
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False
            )

            return Response(
                {"message": "OTP sent successfully."},
                status=status.HTTP_200_OK
            )

        except User.DoesNotExist:
            return Response(
                {"Error": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )


# RESET PASSWORD API
class ResetPasswordAPI(APIView):
    @extend_schema(
    summary="Reset Password",
    request=ResetPasswordSerializer,
    responses=MessageResponseSerializer
)

    def post(self, request):

        email = request.data.get("email")
        otp = request.data.get("otp")
        new_password = request.data.get("new_password")

        if not email or not otp or not new_password:
            return Response(
                {"Error": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)

            if user.otp != otp:
                return Response(
                    {"Error": "Invalid OTP."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user.password = make_password(new_password)
            user.otp = None
            user.save()

            return Response(
                {"message": "Password reset successful."},
                status=status.HTTP_200_OK
            )

        except User.DoesNotExist:
            return Response(
                {"Error": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )


@extend_schema(
    summary="Create Employee or Admin",
    description="Create a new Employee or Admin account.",
    request=SisUserCreateRequestSerializer,
    responses=SisUserCreateResponseSerializer)
class SisUserCreateAPIView(generics.CreateAPIView):
    queryset = SisUser.objects.all()
    serializer_class = SisUserSerializer


# LIST USERS (ADMIN ONLY)
@extend_schema(
    summary="List Employee and Admin",
    description="Retrieve all Employee and Admin accounts.",
    responses=SisUserCreateResponseSerializer)
class SisUserListAPIView(generics.ListAPIView):
    queryset = SisUser.objects.all()
    serializer_class = SisUserSerializer
    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUserRole]


class SisUserLoginAPIView(APIView):

    @extend_schema(
    summary="admin or employee Login",
    description="Authenticate Admin or Employee and return JWT token.",
    request=SisUserLoginSerializer,
    responses=SisUserLoginResponseSerializer)
    def post(self, request):

        serializer = SisUserLoginSerializer(data=request.data)

        if serializer.is_valid():

            username = serializer.validated_data["username"]
            password = serializer.validated_data["password"]

            try:
                user = SisUser.objects.get(username=username)

            except SisUser.DoesNotExist:
                return Response(
                    {"Error": "Invalid username or password."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            if not check_password(password, user.password):
                return Response(
                    {"Error": "Invalid password."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            payload = {
                "sisuser_id": user.id,
                "username": user.username,
                "role": user.choice,
                "exp": datetime.utcnow() + timedelta(days=1)
            }

            token = jwt.encode(
                payload,
                settings.SECRET_KEY,
                algorithm="HS256"
            )

            return Response({
                "token": token,
                "role": user.choice,
                "username": user.username
            })

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
@extend_schema(
    summary="Delete Employee",
    description="Allows Admin users to delete employee accounts.",
    responses=MessageResponseSerializer,
    auth=[{"BearerAuth": []}])
class DeleteEmployeeAPIView(DestroyAPIView):

    queryset = SisUser.objects.filter(choice="employee_role")   
    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [IsSisAdmin]

    def destroy(self, request, *args, **kwargs):
        try:
            employee = self.get_object()

            self.perform_destroy(employee)

            return Response(
                {"message": "User deleted successfully."},
                status=status.HTTP_200_OK
            )

        except Http404:
            return Response(
                {"Error": "Employee not found."},
                status=status.HTTP_404_NOT_FOUND
            )

class DashboardAPIView(APIView):

    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [IsEmployeeOrAdmin]

    @extend_schema(
    summary="Dashboard Access",
    description="Admin and Employee can access dashboard",
    responses=DashboardResponseSerializer)
    def get(self, request):

        return Response({
            "message": "Dashboard Access Granted",
            "user": request.user.username,
            "role": request.user.choice
        })



class ProfileAPIView(APIView):
    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [IsEmployeeOrAdmin]  # OR IsAuthenticated if you want simple
    @extend_schema(
        summary="Get Profile",
        description="Retrieve logged-in user profile",
        responses=ProfileResponseSerializer)
    def get(self, request):
        serializer = ProfileSerializer(request.user)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Update Profile",
        description="Update logged-in user profile (partial update allowed)",
        request=ProfileUpdateSerializer,     # for swagger
        responses={
            200: ProfileResponseSerializer    # for swagger       
        })
    def patch(self, request):
        serializer = ProfileSerializer(
            request.user,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Profile updated successfully",
                "data": serializer.data
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)