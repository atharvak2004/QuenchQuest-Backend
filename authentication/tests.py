from unittest.mock import patch

from django.urls import reverse
from django.contrib.auth.hashers import make_password
from rest_framework.test import APITestCase
from rest_framework import status
import jwt
from datetime import datetime, timedelta
from django.conf import settings
from authentication.models import User, SisUser


class AuthenticationAPITest(APITestCase):

    def setUp(self):

        self.register_url = "/register/"
        self.verify_url = "/verify-otp/"
        self.login_url = "/login/"

        self.user = User.objects.create(
            name="Pratiksha",
            email="pratiksha@gmail.com",
            phone="9876543210",
            gender="female",
            skills="Python",
            location="Pune",
            availability="Weekend",
            password=make_password("Test@123"),
            otp="123456",
            is_verified=False
        )
    
        self.admin = SisUser.objects.create_user(
        username="admin",
        email="admin@gmail.com",
        password="Admin123",
        choice="admin"
      )

        self.employee = SisUser.objects.create_user(
        username="employee",
        email="employee@gmail.com",
        password="Employee123",
        choice="employee_role"
    )        



    @patch("authentication.views.send_mail")
    def test_register_success(self, mock_send_mail):

        data = {
            "name": "John",
            "email": "john@gmail.com",
            "phone": "9999999999",
            "gender": "male",
            "skills": "Python",
            "location": "Pune",
            "availability": "Weekend",
            "password": "Test@123"
        }

        response = self.client.post(self.register_url, data)

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

        self.assertTrue(
            User.objects.filter(
                email="john@gmail.com"
            ).exists()
        )

        mock_send_mail.assert_called_once()        

    def test_register_existing_email(self):

        data = {
            "name": "ABC",
            "email": "pratiksha@gmail.com",
            "phone": "8888888888",
            "gender": "female",
            "skills": "Python",
            "location": "Pune",
            "availability": "Morning",
            "password": "123456"
        }

        response = self.client.post(
            self.register_url,
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )        

    def test_register_missing_fields(self):

        response = self.client.post(
            self.register_url,
            {}
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )        

    @patch("authentication.views.send_mail")
    def test_verify_otp_success(self, mock_send_mail):

        data = {
            "email": "pratiksha@gmail.com",
            "otp": "123456"
        }

        response = self.client.post(
            self.verify_url,
            data
        )

        self.user.refresh_from_db()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        self.assertTrue(
            self.user.is_verified
        )

        mock_send_mail.assert_called_once()        

    def test_verify_invalid_otp(self):

        data = {
            "email": "pratiksha@gmail.com",
            "otp": "999999"
        }

        response = self.client.post(
            self.verify_url,
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )        

    def test_verify_user_not_found(self):

        data = {
            "email": "abc@gmail.com",
            "otp": "123456"
        }

        response = self.client.post(
            self.verify_url,
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND
        )        

    def test_login_success(self):

        self.user.is_verified = True
        self.user.save()

        data = {
            "email": "pratiksha@gmail.com",
            "password": "Test@123"
        }

        response = self.client.post(
            self.login_url,
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        self.assertIn(
            "token",
            response.data
        )        

    def test_login_wrong_password(self):

        self.user.is_verified = True
        self.user.save()

        data = {
            "email": "pratiksha@gmail.com",
            "password": "WrongPassword"
        }

        response = self.client.post(
            self.login_url,
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )        

    def test_login_unverified_user(self):

        data = {
            "email": "pratiksha@gmail.com",
            "password": "Test@123"
        }

        response = self.client.post(
            self.login_url,
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )        

    def test_login_user_not_found(self):

        data = {
            "email": "xyz@gmail.com",
            "password": "Test@123"
        }

        response = self.client.post(
            self.login_url,
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )        

    @patch("authentication.views.send_mail")
    def test_forgot_password_success(self, mock_send_mail):

        data = {
            "email": "pratiksha@gmail.com"
        }

        response = self.client.post("/forgot-password/", data)

        self.user.refresh_from_db()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        self.assertIsNotNone(self.user.otp)

        mock_send_mail.assert_called_once()

    def test_forgot_password_user_not_found(self):

        data = {
            "email": "abc@gmail.com"
        }

        response = self.client.post(
            "/forgot-password/",
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND
        )

    def test_forgot_password_missing_email(self):

        response = self.client.post(
            "/forgot-password/",
            {}
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )        

    def test_reset_password_success(self):

        self.user.otp = "999999"
        self.user.save()

        data = {
            "email": "pratiksha@gmail.com",
            "otp": "999999",
            "new_password": "NewPassword123"
        }

        response = self.client.post(
            "/reset-password/",
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )        

    def test_reset_password_invalid_otp(self):

        self.user.otp = "999999"
        self.user.save()

        data = {
            "email": "pratiksha@gmail.com",
            "otp": "123456",
            "new_password": "NewPassword123"
        }

        response = self.client.post(
            "/reset-password/",
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )        

    def test_reset_password_user_not_found(self):

        data = {
            "email": "xyz@gmail.com",
            "otp": "123456",
            "new_password": "Password123"
        }

        response = self.client.post(
            "/reset-password/",
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND
        )        

    def test_reset_password_missing_fields(self):

        response = self.client.post(
            "/reset-password/",
            {}
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )        

    def test_create_sisuser_success(self):

        data = {
            "username": "employee1",
            "email": "employee@gmail.com",
            "phone": "9876543211",
            "location": "Pune",
            "password": "Employee123",
            "choice": "employee_role"
        }

        response = self.client.post(
            "/sisuser/create/",
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

        self.assertTrue(
            SisUser.objects.filter(
                username="employee1"
            ).exists()
        )        

    def test_create_duplicate_username(self):

        data = {
    "username": self.admin.username,
    "email": "newuser@gmail.com",
    "phone": "9999999999",
    "location": "Pune",
    "password": "Admin123",
    "choice": "admin"
}

        response = self.client.post(
            "/sisuser/create/",
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )        

    def test_sisuser_login_success(self):

        data = {
    "username": self.admin.username,
    "password": "Admin123"
}

        response = self.client.post(
            "/sisuser/login/",
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        self.assertIn(
            "token",
            response.data
        )        

    def test_sisuser_login_invalid_username(self):

        data = {
            "username": "wronguser",
            "password": "Admin123"
        }

        response = self.client.post(
            "/sisuser/login/",
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED
        )

    def test_sisuser_login_invalid_password(self):

        data = {
    "username": self.admin.username,
    "password": "Admin12"
}

        response = self.client.post(
            "/sisuser/login/",
            data
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED
        )

    def test_sisuser_login_missing_fields(self):

        response = self.client.post(
            "/sisuser/login/",
            {}
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )        





    def get_admin_token(self):

     payload = {
        "sisuser_id": self.admin.id,
        "username": self.admin.username,
        "role": self.admin.choice,
        "exp": datetime.utcnow() + timedelta(days=1)
    }

     return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm="HS256"
    )


    def get_employee_token(self):

     payload = {
        "sisuser_id": self.employee.id,
        "username": self.employee.username,
        "role": self.employee.choice,
        "exp": datetime.utcnow() + timedelta(days=1)
    }

     return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm="HS256"
    )

    def test_dashboard_admin(self):

     token = self.get_admin_token()

     self.client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}"
    )

     response = self.client.get("/dashboard/")

     self.assertEqual(
        response.status_code,
        status.HTTP_200_OK
    )


    def test_dashboard_employee(self):

     token = self.get_employee_token()

     self.client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}"
    )

     response = self.client.get("/dashboard/")

     self.assertEqual(
        response.status_code,
        status.HTTP_200_OK
    )


    def test_dashboard_without_token(self):

     response = self.client.get("/dashboard/")

     self.assertEqual(
        response.status_code,
        status.HTTP_401_UNAUTHORIZED
    )


    def test_dashboard_invalid_token(self):

     self.client.credentials(
        HTTP_AUTHORIZATION="Bearer invalidtoken"
    )

     response = self.client.get("/dashboard/")

     self.assertEqual(
        response.status_code,
        status.HTTP_401_UNAUTHORIZED
    )

    def test_profile_get(self):

     token = self.get_employee_token()

     self.client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}"
    )

     response = self.client.get("/profile/")

     self.assertEqual(
        response.status_code,
        status.HTTP_200_OK
    )

     self.assertEqual(
        response.data["username"],
        "employee"
    )

    def test_profile_patch(self):

     token = self.get_employee_token()

     self.client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}"
    )

     response = self.client.patch(
        "/profile/",
        {
            "phone": "9999999999",
            "location": "Mumbai"
        },
        format="json"
    )

     self.assertEqual(
        response.status_code,
        status.HTTP_200_OK
    )

     self.employee.refresh_from_db()

     self.assertEqual(
        self.employee.phone,
        "9999999999"
    )

    def test_profile_without_token(self):

     response = self.client.get("/profile/")

     self.assertEqual(
        response.status_code,
        status.HTTP_401_UNAUTHORIZED
    )

    def test_delete_employee_by_admin(self):

     token = self.get_admin_token()

     self.client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}"
    )

     response = self.client.delete(
        f"/employee/delete/{self.employee.id}/"
    )

     self.assertEqual(
        response.status_code,
        status.HTTP_200_OK
    )

     self.assertFalse(
        SisUser.objects.filter(
            id=self.employee.id
        ).exists()
    )

    def test_employee_cannot_delete_employee(self):

     token = self.get_employee_token()

     self.client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}"
    )

     another = SisUser.objects.create_user(
        username="employee2",
        email="employee2@gmail.com",
        password="Employee123",
        choice="employee_role"
    )

     response = self.client.delete(
        f"/employee/delete/{another.id}/"
    )

     self.assertEqual(
        response.status_code,
        status.HTTP_403_FORBIDDEN
    )

    def test_delete_without_token(self):

     response = self.client.delete(
        f"/employee/delete/{self.employee.id}/"
    )

     self.assertEqual(
        response.status_code,
        status.HTTP_401_UNAUTHORIZED
    )        
    
    
    def test_delete_invalid_employee(self):

     token = self.get_admin_token()

     self.client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}"
    )

     response = self.client.delete(
        "/employee/delete/9999/"
    )

     self.assertEqual(
        response.status_code,
        status.HTTP_404_NOT_FOUND
    )

    def test_admin_can_access_profile(self):

     token = self.get_admin_token()

     self.client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}"
    )

     response = self.client.get("/profile/")

     self.assertEqual(
        response.status_code,
        status.HTTP_200_OK
    )


    def test_employee_can_access_profile(self):

     token = self.get_employee_token()

     self.client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}"
    )

     response = self.client.get("/profile/")

     self.assertEqual(
        response.status_code,
        status.HTTP_200_OK
    )



     