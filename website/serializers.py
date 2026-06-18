from rest_framework import serializers
from .models import *

class OurImpactSerializer(serializers.ModelSerializer):

    class Meta:
        model = OurImpact
        fields = "__all__"


class LeadershipSerializer(serializers.ModelSerializer):

    class Meta:
        model = Leadership
        fields = "__all__"


class ProgramCardSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProgramCard
        fields = "__all__"


class UserSearchSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    volunteer_id = serializers.CharField()


class UserSearchResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    returned = serializers.IntegerField()
    results = UserSearchSerializer(many=True)