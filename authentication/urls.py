from django.urls import path
from .views import *

urlpatterns = [
    path("register/", RegisterAPI.as_view()),
    path("verify-otp/", VerifyOTPAPI.as_view()),
    path("login/", LoginAPI.as_view()),
    path("forgot-password/", ForgotPasswordAPI.as_view()),
    path("reset-password/", ResetPasswordAPI.as_view()),
    path("sisuser/create/", SisUserCreateAPIView.as_view()),
    path("sisuser/list/", SisUserListAPIView.as_view()),
    path("sisuser/login/",SisUserLoginAPIView.as_view(),name="sisuser-login"),
    path("dashboard/", DashboardAPIView.as_view()),
    path("employee/delete/<int:pk>/", DeleteEmployeeAPIView.as_view()), 
    path("profile/", ProfileAPIView.as_view(), name="profile"),

]

