from django.urls import path
from .views import ContactAPI

urlpatterns = [
    path('', ContactAPI.as_view()),
    path('<int:pk>/', ContactAPI.as_view()),
]