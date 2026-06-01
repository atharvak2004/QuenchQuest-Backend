from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from authentication.models import User
from .models import Contact


class ContactAPI(APIView):

    def post(self, request):

        user_id = request.data.get("user")
        message = request.data.get("message")

        # message is ALWAYS required
        if not message:
            return Response(
                {"message": "Message is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # CASE 1: Logged-in user
        if user_id:

            try:
                user = User.objects.get(id=user_id)

                Contact.objects.create(
                    user=user,
                    message=message
                )

                return Response(
                    {"message": "Message sent successfully."},
                    status=status.HTTP_201_CREATED
                )

            except User.DoesNotExist:
                return Response(
                    {"message": "You are not registered. Please register first."},
                    status=status.HTTP_404_NOT_FOUND
                )

        # CASE 2: Guest user
        else:

            name = request.data.get("name")
            contact = request.data.get("contact")
            email = request.data.get("email")
            address = request.data.get("address")

            if not all([name, contact, email, address]):
                return Response(
                    {"message": "All fields are required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            Contact.objects.create(
                name=name,
                contact=contact,
                email=email,
                address=address,
                message=message
            )

            return Response(
                {"message": "Message sent successfully."},
                status=status.HTTP_201_CREATED
            )