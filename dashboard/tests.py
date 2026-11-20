from rest_framework import status
from rest_framework.test import APITestCase

from authentication.models import SisUser, User
from authentication.utils import generate_token
from dashboard.models import Beneficiary, Campaign, Donation


class DashboardCrudAPITest(APITestCase):

    def setUp(self):
        self.volunteer = User.objects.create(
            name="Vol", email="vol@example.com", phone="9000000000", password="x", is_verified=True
        )
        self.admin = SisUser.objects.create_user(
            username="admin", email="admin@example.com", password="Admin123", choice="admin"
        )
        login = self.client.post(
            "/api/auth/sisuser/login/", {"username": "admin", "password": "Admin123"}
        )
        self.admin_token = login.data["token"]
        self.volunteer_token = generate_token(self.volunteer)

    def as_admin(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.admin_token}")

    def as_volunteer(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.volunteer_token}")

    def test_campaigns_require_login(self):
        self.assertEqual(self.client.get("/api/dashboard/campaigns/").status_code, 401)

    def test_admin_token_works_on_campaigns(self):
        self.as_admin()
        res = self.client.post(
            "/api/dashboard/campaigns/", {"title": "Water", "description": "Wells"}
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.client.get("/api/dashboard/campaigns/").status_code, 200)

    def test_volunteer_can_read_but_not_create_campaigns(self):
        Campaign.objects.create(title="A", description="B", is_published=True)
        Campaign.objects.create(title="Draft", description="hidden")
        self.as_volunteer()
        self.assertEqual(len(self.client.get("/api/dashboard/campaigns/").data), 1)
        res = self.client.post("/api/dashboard/campaigns/", {"title": "X", "description": "Y"})
        self.assertEqual(res.status_code, 403)

    def test_volunteer_beneficiary_attaches_self(self):
        self.as_volunteer()
        res = self.client.post("/api/dashboard/beneficiaries/", {"age": 10, "need": "Books"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Beneficiary.objects.get().user, self.volunteer)

    def test_volunteer_donation_attaches_self_and_sees_own(self):
        other = User.objects.create(name="O", email="o@example.com", password="x")
        Donation.objects.create(donor=other, amount=5)
        self.as_volunteer()
        res = self.client.post("/api/dashboard/donations/", {"amount": "100.00"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["donor"], self.volunteer.id)
        self.assertEqual(len(self.client.get("/api/dashboard/donations/").data), 1)

    def test_admin_donation_requires_donor(self):
        self.as_admin()
        res = self.client.post("/api/dashboard/donations/", {"amount": "10.00"})
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            "/api/dashboard/donations/", {"amount": "10.00", "donor": self.volunteer.id}
        )
        self.assertEqual(res.status_code, 201)

    def test_volunteer_update_and_users_list_are_staff_only(self):
        self.assertEqual(self.client.get("/api/dashboard/users/").status_code, 401)
        res = self.client.patch(f"/api/dashboard/volunteers/{self.volunteer.id}/", {"name": "Hacked"})
        self.assertEqual(res.status_code, 401)
        self.as_admin()
        self.assertEqual(self.client.get("/api/dashboard/users/").status_code, 200)
