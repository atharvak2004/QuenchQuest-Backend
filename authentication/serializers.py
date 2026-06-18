from rest_framework import serializers
from .models import User
from .models import SisUser
from django.contrib.auth import get_user_model



class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField()
    gender = serializers.CharField()
    skills = serializers.CharField()
    location = serializers.CharField(required=False, allow_blank=True)
    availability = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField()

    def create(self, validated_data):
        return User.objects.create(**validated_data)


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField()
    new_password = serializers.CharField()


class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class SisUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = SisUser
        fields = [
            "id",
            "username",
            "email",
            "phone",
            "location",
            "password",
            "choice"
        ]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = SisUser(**validated_data)
        user.set_password(password)
        user.save()
        return user
    

class SisUserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


    User = get_user_model()
from rest_framework import serializers
from .models import SisUser

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SisUser
        fields = [
            "id",
            "username",
            "email",
            "phone",
            "location",
            "choice"  # role (admin/employee)
        ]
        read_only_fields = ["id", "choice"]