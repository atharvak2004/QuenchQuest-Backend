import io
import json
import urllib.error
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image

from adminpanel.tests import AdminAPITestBase, png_file
from authentication.google import GoogleTokenError, GoogleUnavailable, verify_credential
from authentication.models import User
from authentication.tokens import issue_tokens
from contact.models import Contact
from dashboard.models import Campaign, CampaignVolunteer, Donation
from website.models import Project, ProjectVolunteer, Service

from .models import CODE_ALPHABET, Attendance, AttendanceCode


class VolunteeringTestBase(AdminAPITestBase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.service = Service.objects.create(title="Water", is_published=True)
        self.project = Project.objects.create(
            title="Clean Water Kolhapur", service=self.service, status="active", is_published=True,
            location_name="Kolhapur, Maharashtra", latitude=Decimal("16.705"), longitude=Decimal("74.2433"),
        )

    def join(self, project=None, user=None):
        ProjectVolunteer.objects.create(project=project or self.project, volunteer=user or self.volunteer, joined_by="self")

    def make_code(self, project=None, **extra):
        defaults = {"valid_until": timezone.now() + timedelta(hours=2)}
        return AttendanceCode.objects.create(project=project or self.project, **{**defaults, **extra})


# ---------------------------------------------------------------------------
# Joining projects
# ---------------------------------------------------------------------------

class ProjectJoinTests(VolunteeringTestBase):

    def url(self, project=None):
        return f"/api/projects/{(project or self.project).pk}/join/"

    def test_requires_volunteer_token(self):
        self.assertEqual(self.client.post(self.url()).status_code, 401)
        self.login(self.admin)
        self.assertEqual(self.client.post(self.url()).status_code, 401)

    def test_join_and_leave(self):
        self.login(self.volunteer)
        res = self.client.post(self.url())
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json(), {"message": "You've joined this project.", "has_joined": True, "volunteer_count": 1})
        self.assertEqual(self.client.post(self.url()).status_code, 200)
        self.assertEqual(ProjectVolunteer.objects.get().joined_by, "self")

        res = self.client.delete(self.url())
        self.assertEqual(res.json()["has_joined"], False)
        self.assertFalse(ProjectVolunteer.objects.exists())

    def test_join_rules(self):
        closed = Project.objects.create(title="Closed", status="active", is_published=True, allow_volunteers=False)
        done = Project.objects.create(title="Done", status="completed", is_published=True)
        paused = Project.objects.create(title="Paused", status="paused", is_published=True)
        soon = Project.objects.create(title="Soon", status="concept", is_published=True)
        draft = Project.objects.create(title="Draft", status="active")
        self.login(self.volunteer)
        self.assertEqual(self.client.post(self.url(closed)).status_code, 400)
        self.assertEqual(self.client.post(self.url(done)).status_code, 400)
        self.assertEqual(self.client.post(self.url(paused)).status_code, 400)
        self.assertEqual(self.client.post(self.url(soon)).status_code, 201)
        self.assertEqual(self.client.post(self.url(draft)).status_code, 404)

    def test_public_project_fields(self):
        self.assertIsNone(self.client.get(f"/api/website/projects/{self.project.slug}/").json()["has_joined"])
        self.client.credentials(HTTP_AUTHORIZATION="Bearer stale")
        self.assertEqual(self.client.get("/api/website/projects/").status_code, 200)

        self.login(self.volunteer)
        card = self.client.get("/api/website/projects/").json()["results"][0]
        self.assertFalse(card["has_joined"])
        self.assertTrue(card["allow_volunteers"])
        self.assertEqual(card["service_title"], "Water")
        self.join()
        detail = self.client.get(f"/api/website/projects/{self.project.slug}/").json()
        self.assertTrue(detail["has_joined"])

    def test_status_list_and_joinable_filters(self):
        Project.objects.create(title="Soon", status="concept", is_published=True)
        Project.objects.create(title="Done", status="completed", is_published=True)
        Project.objects.create(title="Closed", status="active", is_published=True, allow_volunteers=False)
        self.assertEqual(self.client.get("/api/website/projects/?status=active,concept").json()["count"], 3)
        joinable = self.client.get("/api/website/projects/?joinable=true").json()["results"]
        self.assertEqual(sorted(p["title"] for p in joinable), ["Clean Water Kolhapur", "Soon"])

    def test_my_projects(self):
        self.join()
        # Added by staff through the admin panel
        other = Project.objects.create(title="Health camp", status="concept", is_published=True)
        self.login(self.employee)
        self.client.post(f"/api/admin/projects/{other.pk}/volunteers/", {"volunteer_ids": [self.volunteer.pk]}, format="json")
        Attendance.objects.create(project=self.project, volunteer=self.volunteer, method="code", status="approved")

        self.login(self.volunteer)
        res = self.client.get("/api/auth/me/projects/").json()
        self.assertEqual(res["count"], 2)
        by_title = {p["title"]: p for p in res["results"]}
        water = by_title["Clean Water Kolhapur"]
        self.assertEqual(water["joined_by"], "self")
        self.assertEqual(water["latitude"], "16.705000")
        self.assertEqual(water["service_title"], "Water")
        self.assertEqual(water["days_attended"], 1)
        self.assertTrue(water["can_mark_attendance"])
        self.assertEqual(by_title["Health camp"]["joined_by"], "staff")


# ---------------------------------------------------------------------------
# Attendance (volunteer side)
# ---------------------------------------------------------------------------

class AttendanceTests(VolunteeringTestBase):

    def setUp(self):
        super().setUp()
        self.url = f"/api/projects/{self.project.pk}/attendance/"
        self.login(self.volunteer)

    def test_must_join_first(self):
        res = self.client.post(self.url, {"code": "ABCDEF"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_code_is_approved_at_once(self):
        self.join()
        code = self.make_code()
        res = self.client.post(self.url, {"code": code.code.lower()}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()
        self.assertEqual((data["method"], data["status"], data["project_title"]), ("code", "approved", self.project.title))
        self.assertEqual(data["date"], timezone.localdate().isoformat())

        again = self.client.post(self.url, {"code": code.code}, format="json")
        self.assertEqual(again.status_code, 400)
        self.assertIn("already marked present", again.json()["Error"])

    def test_bad_codes(self):
        self.join()
        other = Project.objects.create(title="Other", status="active", is_published=True)
        expired = self.make_code(valid_from=timezone.now() - timedelta(hours=5), valid_until=timezone.now() - timedelta(hours=1))
        off = self.make_code(is_active=False)
        elsewhere = self.make_code(project=other)
        for code in ("NOPE99", expired.code, off.code, elsewhere.code):
            res = self.client.post(self.url, {"code": code}, format="json")
            self.assertEqual(res.status_code, 400, code)

    def test_too_many_wrong_codes(self):
        self.join()
        good = self.make_code()
        for _ in range(5):
            self.client.post(self.url, {"code": "WRONG1"}, format="json")
        res = self.client.post(self.url, {"code": good.code}, format="json")
        self.assertEqual(res.status_code, 429)

    def test_photo_waits_for_approval(self):
        self.join()
        res = self.client.post(self.url, {"photo": png_file(), "latitude": "16.705000", "longitude": "74.243300"},
                               format="multipart")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual((res.json()["method"], res.json()["status"]), ("photo", "pending"))
        record = Attendance.objects.get()
        self.assertTrue(record.photo.name.endswith(".webp"))
        self.assertEqual(record.latitude, Decimal("16.705000"))
        with Image.open(record.photo.path) as stored:
            self.assertEqual(stored.format, "WEBP")

        again = self.client.post(self.url, {"photo": png_file()}, format="multipart")
        self.assertEqual(again.status_code, 400)

        # A staff code still works while the photo is pending, and approves the day.
        res = self.client.post(self.url, {"code": self.make_code().code}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "approved")
        self.assertEqual(Attendance.objects.count(), 1)

    def test_rejected_can_be_sent_again(self):
        self.join()
        Attendance.objects.create(project=self.project, volunteer=self.volunteer, method="photo",
                                  status="rejected", review_note="Photo too dark")
        res = self.client.post(self.url, {"photo": png_file()}, format="multipart")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "pending")
        self.assertEqual(res.json()["review_note"], "")

    def test_validation(self):
        self.join()
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 400)
        res = self.client.post(self.url, {"photo": png_file(), "latitude": "16.7"}, format="multipart")
        self.assertEqual(res.status_code, 400)
        fake = io.BytesIO(b"not an image")
        fake.name = "x.png"
        self.assertEqual(self.client.post(self.url, {"photo": fake}, format="multipart").status_code, 400)

    def test_closed_project(self):
        self.join()
        self.project.status = "completed"
        self.project.save()
        res = self.client.post(self.url, {"code": self.make_code().code}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_history_and_summary(self):
        self.join()
        campaign = Campaign.objects.create(title="Drive", is_published=True, status="active")
        CampaignVolunteer.objects.create(campaign=campaign, volunteer=self.volunteer)
        Donation.objects.create(donor=self.volunteer, amount=Decimal("250.50"))
        Donation.objects.create(donor=self.volunteer, amount=Decimal("49.50"), campaign=campaign)
        Attendance.objects.create(project=self.project, volunteer=self.volunteer, method="code", status="approved",
                                  date=timezone.localdate() - timedelta(days=2))
        Attendance.objects.create(project=self.project, volunteer=self.volunteer, method="photo", status="pending")

        history = self.client.get("/api/auth/me/attendance/").json()
        self.assertEqual(history["count"], 2)
        self.assertEqual(history["results"][0]["status"], "pending")  # newest first
        summary = self.client.get("/api/auth/me/summary/").json()
        self.assertEqual(summary, {
            "projects": 1, "campaigns": 1, "attendance_days": 1, "pending_attendance": 1, "total_donated": "300.00",
            "certificates": 0,
        })


# ---------------------------------------------------------------------------
# Attendance (staff side)
# ---------------------------------------------------------------------------

class AttendanceAdminTests(VolunteeringTestBase):

    def setUp(self):
        super().setUp()
        self.login(self.employee)

    def test_create_and_switch_off_codes(self):
        res = self.client.post("/api/admin/attendance-codes/", {
            "project": self.project.pk, "valid_hours": 2, "note": "Saturday session",
        }, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        code = res.json()
        self.assertEqual(len(code["code"]), 6)
        self.assertTrue(set(code["code"]) <= set(CODE_ALPHABET))
        self.assertTrue(code["is_valid_now"])
        self.assertEqual(code["created_by_name"], "emp")

        self.assertEqual(self.client.get("/api/admin/attendance-codes/?valid=true").json()["count"], 1)
        self.client.delete(f"/api/admin/attendance-codes/{code['id']}/")
        self.assertEqual(self.client.get("/api/admin/attendance-codes/?valid=true").json()["count"], 0)

        too_long = self.client.post("/api/admin/attendance-codes/", {"project": self.project.pk, "valid_hours": 100}, format="json")
        self.assertEqual(too_long.status_code, 400)

    def test_editor_has_no_access(self):
        self.login(self.editor)
        self.assertEqual(self.client.get("/api/admin/attendance/").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/attendance-codes/").status_code, 403)

    def test_review_flow(self):
        self.join()
        self.login(self.volunteer)
        self.client.post(f"/api/projects/{self.project.pk}/attendance/", {"photo": png_file()}, format="multipart")

        self.login(self.employee)
        pending = self.client.get("/api/admin/attendance/?status=pending").json()
        self.assertEqual(pending["count"], 1)
        record = pending["results"][0]
        self.assertTrue(record["photo"].startswith("http://testserver/media/attendance/"))
        self.assertEqual(record["volunteer_code"], self.volunteer.volunteer_id)
        self.assertEqual(self.client.get("/api/admin/dashboard/").json()["attendance"]["pending"], 1)

        res = self.client.post(f"/api/admin/attendance/{record['id']}/reject/", {"note": "Photo too dark"}, format="json")
        self.assertEqual(res.json()["status"], "rejected")
        self.assertEqual(res.json()["reviewed_by_name"], "emp")

        self.login(self.volunteer)
        mine = self.client.get("/api/auth/me/attendance/").json()["results"][0]
        self.assertEqual((mine["status"], mine["review_note"]), ("rejected", "Photo too dark"))

        self.login(self.employee)
        res = self.client.post(f"/api/admin/attendance/{record['id']}/approve/", {}, format="json")
        self.assertEqual(res.json()["status"], "approved")

    def test_bulk_approve_and_export(self):
        other = User.objects.create(name="Amit", email="amit@example.com", password="x", is_verified=True)
        a = Attendance.objects.create(project=self.project, volunteer=self.volunteer, method="photo", status="pending")
        b = Attendance.objects.create(project=self.project, volunteer=other, method="photo", status="pending")
        res = self.client.post("/api/admin/attendance/bulk-approve/", {"ids": [a.pk, b.pk]}, format="json")
        self.assertEqual(res.json()["approved"], 2)
        export = self.client.get(f"/api/admin/attendance/export/?project={self.project.pk}")
        lines = export.content.decode("utf-8-sig").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("approved", lines[1])

    def test_staff_cannot_create_attendance_directly(self):
        res = self.client.post("/api/admin/attendance/", {}, format="json")
        self.assertEqual(res.status_code, 405)


# ---------------------------------------------------------------------------
# Google sign-in
# ---------------------------------------------------------------------------

CLAIMS = {"sub": "google-123", "email": "Priya@Example.com", "name": "Priya Shah", "email_verified": "true"}


@override_settings(GOOGLE_CLIENT_ID="client-id.apps.googleusercontent.com")
class GoogleLoginTests(AdminAPITestBase):
    url = "/api/auth/google/"

    def post(self, claims=CLAIMS, side_effect=None):
        with patch("authentication.views.verify_credential", return_value=claims, side_effect=side_effect):
            return self.client.post(self.url, {"credential": "id-token"}, format="json")

    @override_settings(GOOGLE_CLIENT_ID="")
    def test_switched_off_without_client_id(self):
        self.assertEqual(self.client.post(self.url, {"credential": "x"}, format="json").status_code, 501)

    def test_first_login_creates_volunteer(self):
        res = self.post()
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()
        self.assertTrue(data["created"])
        self.assertFalse(data["profile_complete"])
        self.assertEqual(data["user"]["email"], "priya@example.com")
        self.assertTrue(data["user"]["volunteer_id"].startswith("QQ"))
        user = User.objects.get(email="priya@example.com")
        self.assertTrue(user.is_verified)
        self.assertFalse(user.password.startswith("pbkdf2"))  # unusable password

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {data['token']}")
        self.assertEqual(self.client.get("/api/auth/me/").json()["name"], "Priya Shah")

        again = self.post()
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.json()["created"])
        self.assertEqual(User.objects.filter(email="priya@example.com").count(), 1)

    def test_links_existing_email_account_and_verifies_it(self):
        pending = User.objects.create(name="Priya", email="priya@example.com", phone="9", skills="Art",
                                      password="x", is_verified=False, otp="123456")
        res = self.post()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["profile_complete"])
        pending.refresh_from_db()
        self.assertEqual((pending.google_sub, pending.is_verified, pending.otp), ("google-123", True, None))

    def test_refusals(self):
        User.objects.create(name="Old", email="priya@example.com", password="x", google_sub="other-sub")
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(self.post(side_effect=GoogleTokenError("bad")).status_code, 401)
        self.assertEqual(self.post(side_effect=GoogleUnavailable("down")).status_code, 503)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 400)

    def test_deactivated_volunteer(self):
        User.objects.create(name="P", email="priya@example.com", password="x", is_active=False)
        self.assertEqual(self.post().status_code, 403)


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@override_settings(GOOGLE_CLIENT_ID="client-id")
class VerifyCredentialTests(AdminAPITestBase):

    def claims(self, **extra):
        base = {"aud": "client-id", "iss": "https://accounts.google.com", "email_verified": "true",
                "exp": str(int(timezone.now().timestamp()) + 600), "sub": "1", "email": "a@example.com"}
        return _FakeResponse(json.dumps({**base, **extra}).encode())

    def test_accepts_a_good_token(self):
        with patch("authentication.google.urllib.request.urlopen", return_value=self.claims()):
            self.assertEqual(verify_credential("t")["sub"], "1")

    def test_rejects_bad_tokens(self):
        for bad in ({"aud": "someone-else"}, {"iss": "evil.example"}, {"email_verified": "false"},
                    {"exp": "1"}, {"sub": ""}):
            with patch("authentication.google.urllib.request.urlopen", return_value=self.claims(**bad)):
                with self.assertRaises(GoogleTokenError, msg=bad):
                    verify_credential("t")
        error = urllib.error.HTTPError("u", 400, "bad", {}, None)
        with patch("authentication.google.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(GoogleTokenError):
                verify_credential("t")


# ---------------------------------------------------------------------------
# Contact form: project
# ---------------------------------------------------------------------------

class ContactProjectTests(VolunteeringTestBase):
    guest = {"name": "Amit", "contact": "9000000000", "email": "amit@example.com", "address": "Pune",
             "message": "I'd like to help"}

    def test_guest_message_with_project(self):
        res = self.client.post("/api/contact/", {**self.guest, "project": self.project.pk}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Contact.objects.get().project, self.project)

        self.login(self.employee)
        inbox = self.client.get(f"/api/admin/contacts/?project={self.project.pk}").json()
        self.assertEqual(inbox["count"], 1)
        self.assertEqual(inbox["results"][0]["project_title"], self.project.title)

    def test_bad_project(self):
        draft = Project.objects.create(title="Draft")
        for value in (draft.pk, 99999, "abc"):
            res = self.client.post("/api/contact/", {**self.guest, "project": value}, format="json")
            self.assertEqual(res.status_code, 400, value)
        self.assertFalse(Contact.objects.exists())

    def test_without_project_still_works(self):
        self.assertEqual(self.client.post("/api/contact/", self.guest, format="json").status_code, 201)


# ---------------------------------------------------------------------------
# Migration: existing project volunteers are kept
# ---------------------------------------------------------------------------

class ProjectVolunteerMigrationTests(TransactionTestCase):
    before = [("website", "0005_programcards_to_services")]
    after = [("website", "0006_project_volunteer_membership")]

    def test_existing_assignments_survive(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old = executor.loader.project_state(self.before).apps
        OldUser, OldProject = old.get_model("authentication", "User"), old.get_model("website", "Project")
        volunteer = OldUser.objects.create(name="V", email="v@example.com", password="x", volunteer_id="QQ001")
        project = OldProject.objects.create(title="P", slug="p")
        project.volunteers.add(volunteer)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.after)
        new = executor.loader.project_state(self.after).apps
        rows = list(new.get_model("website", "ProjectVolunteer").objects.values("project_id", "volunteer_id", "joined_by"))
        self.assertEqual(rows, [{"project_id": project.pk, "volunteer_id": volunteer.pk, "joined_by": "staff"}])

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
