from django.urls import path
from .views import *

urlpatterns = [
    path("register/", RegisterAPI.as_view()),
    path("verify-otp/", VerifyOTPAPI.as_view()),
    path("login/", LoginAPI.as_view()),
    path("forgot-password/", ForgotPasswordAPI.as_view()),
    path("reset-password/", ResetPasswordAPI.as_view()),

]