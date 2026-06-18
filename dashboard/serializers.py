
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