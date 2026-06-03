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


