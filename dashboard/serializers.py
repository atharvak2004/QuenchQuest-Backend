
from rest_framework import serializers
from .models import User


class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "volunteer_id",
            "name",
            "email",
            "gender",
            "phone",
            "skills",
            "location",
            "availability",
            "is_verified",
            "created_at",
        ]

class CreateVolunteerSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField()
    gender = serializers.CharField()
    skills = serializers.CharField()
    location = serializers.CharField(required=False, allow_blank=True)
    availability = serializers.CharField(required=False, allow_blank=True)

class VolunteerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "name",
            "email",
            "phone",
            "gender",
            "skills",
            "location",
            "availability",
            "is_verified"
        ]


# class CampaignSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Campaign
#         fields = "__all__"


# from rest_framework import serializers
# from .models import Beneficiary

# class BeneficiarySerializer(serializers.ModelSerializer):
#     user_name = serializers.CharField(source="user.name", read_only=True)
#     user_email = serializers.CharField(source="user.email", read_only=True)

#     class Meta:
#         model = Beneficiary
#         fields = [
#             "id",
#             "user",
#             "user_name",
#             "user_email",
#             "age",
#             "need",
#             "location",
#             "status",
#             "created_at",
#         ]
#         read_only_fields = ["id", "created_at"]

# class DonationSerializer(serializers.ModelSerializer):
#     donor_name = serializers.CharField(source="donor.name", read_only=True)

#     class Meta:
#         model = Donation
#         fields = [
#             "id",
#             "donor",
#             "donor_name",
#             "amount",
#             "created_at"
#         ]