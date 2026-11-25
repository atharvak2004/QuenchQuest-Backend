import random

from django.utils import timezone
from .tokens import issue_tokens, user_from_refresh
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
            user.otp_sent_at = timezone.now()
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

            to = [settings.ADMIN_NOTIFICATION_EMAIL]

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
    responses=LoginResponseSerializer)

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
            if not user.is_active:
                return Response(
                    {"Error": "This account has been deactivated. Please contact us."},
                    status=status.HTTP_403_FORBIDDEN
                )
            tokens = issue_tokens(user)
            return Response(
                {
                    "message": "Login successful.",
                    "user": {
                         "id": user.id,
                         "volunteer_id": user.volunteer_id,
                         "name": user.name,
                         "email": user.email,
                         "phone": user.phone,
                         "gender": user.gender,
                         "skills": user.skills,
                         "location": user.location,
                         "availability": user.availability,
        },
                    "token": tokens["token"],
                    "refresh": tokens["refresh"],
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
            user.otp_sent_at = timezone.now()
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
    # Only an existing admin may create employee/admin accounts.
    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [IsSisAdmin]


# LIST USERS (ADMIN ONLY)
@extend_schema(
    summary="List Employee and Admin",
    description="Retrieve all Employee and Admin accounts.",
    responses=SisUserCreateResponseSerializer(many=True))
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

            user = SisUser.objects.filter(username=username).first()
            if not user:
                return Response(
                    {"Error": "Invalid username or password."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            now = timezone.now()
            if user.locked_until and user.locked_until > now:
                minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
                return Response(
                    {"Error": f"Too many failed attempts. Try again in {minutes} minute(s)."},
                    status=status.HTTP_403_FORBIDDEN
                )

            if not check_password(password, user.password):
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= SisUser.MAX_FAILED_LOGINS:
                    user.locked_until = now + timedelta(minutes=SisUser.LOCK_MINUTES)
                    user.failed_login_attempts = 0
                user.save(update_fields=["failed_login_attempts", "locked_until"])
                return Response(
                    {"Error": "Invalid username or password."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            if not user.is_active:
                return Response(
                    {"Error": "This account has been deactivated."},
                    status=status.HTTP_403_FORBIDDEN
                )

            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login = now
            user.save(update_fields=["failed_login_attempts", "locked_until", "last_login"])

            tokens = issue_tokens(user)
            return Response({
                "token": tokens["token"],
                "refresh": tokens["refresh"],
                "id": user.id,
                "role": user.choice,
                "username": user.username,
                "modules": sorted(user.modules),
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


# ---------------------------------------------------------------------------
# Tokens, "me", resend OTP, change password
# ---------------------------------------------------------------------------

class TokenRefreshAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get_authenticate_header(self, request):
        # So a bad/expired refresh token is a 401 (log in again), not a 403.
        return "Bearer"

    @extend_schema(
        summary="Refresh token",
        description="Exchange a refresh token (volunteer or staff) for a new access + refresh token pair.",
        request=TokenRefreshRequestSerializer,
        responses=TokenPairSerializer)
    def post(self, request):
        serializer = TokenRefreshRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = user_from_refresh(serializer.validated_data["refresh"])
        return Response(issue_tokens(user))


class MeAPIView(APIView):
    """The logged-in volunteer's own profile."""

    authentication_classes = [UserJWTAuthentication]
    permission_classes = [IsVolunteer]

    @extend_schema(summary="Get my volunteer profile", responses=MeSerializer)
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    @extend_schema(summary="Update my volunteer profile", request=MeSerializer, responses=MeSerializer)
    def patch(self, request):
        serializer = MeSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


OTP_RESEND_COOLDOWN_SECONDS = 60


def send_verification_otp(user):
    """Create a new OTP for an unverified volunteer and email it."""
    otp = str(random.randint(100000, 999999))
    user.otp = otp
    user.otp_sent_at = timezone.now()
    user.save(update_fields=["otp", "otp_sent_at"])
    send_mail(
        "OTP Verification - QuenchQuest",
        f"""
Hello {user.name},

Your new OTP for email verification is: {otp}

Please do not share this OTP with anyone.

Regards,
QuenchQuest Team
""",
        settings.EMAIL_HOST_USER,
        [user.email],
        fail_silently=False,
    )


class ResendOTPAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="Resend verification OTP",
        description="Send a new OTP to an unverified volunteer. One request per minute.",
        request=ForgotPasswordSerializer,
        responses=MessageResponseSerializer)
    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"Error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email=email).first()
        if not user:
            return Response({"Error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        if user.is_verified:
            return Response({"Error": "This email is already verified."}, status=status.HTTP_400_BAD_REQUEST)

        if user.otp_sent_at:
            wait = OTP_RESEND_COOLDOWN_SECONDS - (timezone.now() - user.otp_sent_at).total_seconds()
            if wait > 0:
                return Response(
                    {"Error": f"Please wait {int(wait) + 1} seconds before asking for a new OTP."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        send_verification_otp(user)
        return Response({"message": "A new OTP has been sent to your email."})


class ChangePasswordAPIView(APIView):
    """Admin/employee/editor changes their own password. Logs out other sessions."""

    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [IsAnyStaff]

    @extend_schema(
        summary="Change my password (staff)",
        request=ChangePasswordSerializer,
        responses=TokenPairSerializer)
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        # Old tokens stop working; hand back fresh ones so this session continues.
        return Response({"message": "Password changed.", **issue_tokens(request.user)})


# ---------------------------------------------------------------------------
# Sign in with Google
# ---------------------------------------------------------------------------

from .google import GoogleTokenError, GoogleUnavailable, verify_credential


def volunteer_login_payload(user):
    return {
        "id": user.id,
        "volunteer_id": user.volunteer_id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "gender": user.gender,
        "skills": user.skills,
        "location": user.location,
        "availability": user.availability,
        "is_verified": user.is_verified,
    }


class GoogleLoginAPIView(APIView):
    """Exchange a Google ID token for QuenchQuest tokens. Creates the volunteer on first use."""

    authentication_classes = []
    permission_classes = []

    def get_authenticate_header(self, request):
        return "Bearer"

    @extend_schema(
        summary="Sign in with Google",
        description=(
            "Body {\"credential\": \"<Google ID token>\"}. Returns the same tokens as /api/auth/login/, "
            "plus `created` (new account) and `profile_complete` (phone and skills filled in). "
            "501 when GOOGLE_CLIENT_ID isn't set on the server."
        ),
        request=GoogleLoginRequestSerializer,
        responses=GoogleLoginResponseSerializer,
    )
    def post(self, request):
        if not settings.GOOGLE_CLIENT_ID:
            return Response({"Error": "Google sign-in isn't switched on yet."},
                            status=status.HTTP_501_NOT_IMPLEMENTED)

        payload = GoogleLoginRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            claims = verify_credential(payload.validated_data["credential"])
        except GoogleTokenError:
            return Response({"Error": "Google sign-in failed. Please try again."},
                            status=status.HTTP_401_UNAUTHORIZED)
        except GoogleUnavailable:
            return Response({"Error": "Couldn't reach Google. Please try again in a moment."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        sub, email = claims["sub"], claims["email"].strip().lower()
        user = User.objects.filter(google_sub=sub).first()
        created = False

        if user is None:
            user = User.objects.filter(email__iexact=email).first()
            if user and user.google_sub and user.google_sub != sub:
                return Response({"Error": "This email is linked to a different Google account."},
                                status=status.HTTP_409_CONFLICT)

        if user is None:
            user = User(
                name=(claims.get("name") or email.split("@")[0])[:100],
                email=email,
                password=make_password(None),  # no password until they set one via "Forgot password"
                is_verified=True,
                google_sub=sub,
            )
            user.save()
            created = True
            send_mail(
                "Welcome to QuenchQuest",
                f"Hello {user.name},\n\nWelcome to QuenchQuest! Your Volunteer ID is {user.volunteer_id}.\n\n"
                "Please add your phone number and skills on your dashboard so the team can match you to projects.\n\n"
                "Team QuenchQuest",
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=True,
            )
        else:
            if not user.is_active:
                return Response({"Error": "This account has been deactivated. Please contact us."},
                                status=status.HTTP_403_FORBIDDEN)
            changed = []
            if not user.google_sub:
                user.google_sub = sub
                changed.append("google_sub")
            if not user.is_verified:  # Google has confirmed they own this email
                user.is_verified = True
                user.otp = None
                changed += ["is_verified", "otp"]
            if changed:
                user.save(update_fields=changed)

        tokens = issue_tokens(user)
        return Response(
            {
                "message": "Account created." if created else "Login successful.",
                "user": volunteer_login_payload(user),
                "token": tokens["token"],
                "refresh": tokens["refresh"],
                "created": created,
                "profile_complete": user.profile_complete,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
