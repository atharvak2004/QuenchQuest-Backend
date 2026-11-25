from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from authentication.models import User
from .models import Contact
from .serializers import ContactSerializer
from drf_spectacular.utils import extend_schema
from website.models import Project


class ContactAPI(APIView):
    @extend_schema(summary="Submit Contact Form",
    description="Allows registered and guest users to send contact inquiries.",
    operation_id="contact_submit",
    request=ContactSerializer,responses=ContactSerializer)

    def post(self, request):

        user_id = request.data.get("user")
        message = request.data.get("message")

        project = None
        project_id = request.data.get("project")
        if project_id not in (None, ""):
            project = Project.objects.filter(
                pk=project_id if str(project_id).isdigit() else 0, is_published=True, is_archived=False
            ).first()
            if not project:
                return Response({"Error": "Project not found."}, status=status.HTTP_400_BAD_REQUEST)

        # message is ALWAYS required
        if not message:
            return Response(
                {"Error": "Message is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # CASE 1: Logged-in user
   
        if user_id:

            try:
                user = User.objects.get(id=user_id)

                Contact.objects.create(
                    user=user,
                    message=message,
                    project=project,
                )

                return Response(
                    {"message": "Message sent successfully."},
                    status=status.HTTP_201_CREATED
                )

            except User.DoesNotExist:
                return Response(
                    {"Error": "You are not registered. Please register first."},
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
                    {"Error": "All fields are required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            Contact.objects.create(
                name=name,
                contact=contact,
                email=email,
                address=address,
                message=message,
                project=project,
            )

            return Response(
                {"message": "Message sent successfully."},
                status=status.HTTP_201_CREATED
            )
        

