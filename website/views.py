from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import *
from .serializers import *



# Create your views here.


class OurImpactAPI(APIView):

    def get(self, request):

        impacts = OurImpact.objects.all()
        serializer = OurImpactSerializer(impacts,many=True)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
class LatestOurImpactAPI(APIView):

    def get(self, request):
        impact = OurImpact.objects.order_by('-id').first()

        if not impact:
            return Response(
                {"message": "No impact data found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = OurImpactSerializer(impact)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
class LeadershipAPI(APIView):

    def get(self, request):

        leaders = Leadership.objects.all()
        serializer = LeadershipSerializer(leaders,many=True)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


class ProgramCardAPI(APIView):

    def get(self, request):

        cards = ProgramCard.objects.all()
        serializer = ProgramCardSerializer(cards,many=True)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

