import random

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password

from .models import User
from .serializers import UserSerializer


# REGISTER API
class RegisterAPI(APIView):

    def post(self, request):

        name = request.data.get("name")
        email = request.data.get("email")
        phone = request.data.get("phone")
        skills = request.data.get("skills")
        location = request.data.get("location")
        availability = request.data.get("availability")
        password = request.data.get("password")

        if not name or not email or not phone or not skills or not password:
          return Response(
        {"message": "All required fields are mandatory."},
        status=status.HTTP_400_BAD_REQUEST
    )

        if User.objects.filter(email=email).exists():
            return Response(
                {"message": "Email already registered."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = UserSerializer(data=request.data)

        if serializer.is_valid():

            otp = str(random.randint(100000, 999999))

            user = serializer.save(
                password=make_password(password),
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

    def post(self, request):

        email = request.data.get("email")
        otp = request.data.get("otp")

        if not email or not otp:
            return Response(
                {"message": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)

            if user.otp != otp:
                return Response(
                    {"message": "Invalid OTP."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user.is_verified = True
            user.otp = None
            user.save()

            send_mail(
                "Welcome to QuenchQuest",
                f"""
Hello {user.name},

Your account has been successfully verified.

Welcome to QuenchQuest.

Your Volunteer ID is:{user.volunteer_id}

Regards,
QuenchQuest Team
""",
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False
            )

            return Response(
                {
                    "message": "Account verified successfully.",
                    "volunteer_id": user.volunteer_id
                },
                status=status.HTTP_200_OK
            )

        except User.DoesNotExist:
            return Response(
                {"message": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )


# LOGIN API
class LoginAPI(APIView):

    def post(self, request):

        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"message": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)

            if not check_password(password, user.password):
                return Response(
                    {    "message": "The email address or password you entered is incorrect."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not user.is_verified:
                return Response(
                    {"message": "Please verify your email first."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response(
                {
                    "message": "Login successful."
                },
                status=status.HTTP_200_OK
            )

        except User.DoesNotExist:
            return Response(
                {"message": "Invalid credentials."},
                status=status.HTTP_400_BAD_REQUEST
            )


# FORGOT PASSWORD API
class ForgotPasswordAPI(APIView):

    def post(self, request):

        email = request.data.get("email")

        if not email:
            return Response(
                {"message": "Email is required."},
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
                {"message": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )


# RESET PASSWORD API
class ResetPasswordAPI(APIView):

    def post(self, request):

        email = request.data.get("email")
        otp = request.data.get("otp")
        new_password = request.data.get("new_password")

        if not email or not otp or not new_password:
            return Response(
                {"message": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)

            if user.otp != otp:
                return Response(
                    {"message": "Invalid OTP."},
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
                {"message": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )