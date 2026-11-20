from rest_framework import serializers
from .models import User
from .models import SisUser


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


class LoginUserDataSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    volunteer_id = serializers.CharField()
    name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField()
    gender = serializers.CharField(allow_null=True)
    skills = serializers.CharField(allow_null=True)
    location = serializers.CharField(allow_null=True)
    availability = serializers.CharField(allow_null=True)


class LoginResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user = LoginUserDataSerializer()
    token = serializers.CharField()
    refresh = serializers.CharField()


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


#  for swagger serializers

class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SisUser
        fields = [
            "username",
            "email",
            "phone",
            "location"
        ]        

class ProfileResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = SisUser
        fields = [
            "id",
            "username",
            "email",
            "phone",
            "location",
            "choice"
        ]        

class SisUserCreateRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField()
    location = serializers.CharField()
    password = serializers.CharField()
    choice = serializers.CharField()        

class SisUserCreateResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField()
    location = serializers.CharField()
    choice = serializers.CharField()

class SisUserLoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    refresh = serializers.CharField()
    id = serializers.IntegerField()
    role = serializers.CharField()
    username = serializers.CharField()
    modules = serializers.ListField(child=serializers.CharField())    

class DashboardResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user = serializers.CharField()
    role = serializers.CharField()


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class TokenPairSerializer(serializers.Serializer):
    token = serializers.CharField()
    refresh = serializers.CharField()


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "volunteer_id", "name", "email", "phone", "gender",
            "skills", "location", "availability", "is_verified", "created_at",
        ]
        # Email is the login identity; changing it would skip OTP verification.
        read_only_fields = ["id", "volunteer_id", "email", "is_verified", "created_at"]


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)

    def validate_old_password(self, value):
        if not self.context["user"].check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": "Choose a different password."})
        return attrs
