import importlib
import io
from datetime import timedelta
from unittest.mock import patch

from django.apps import apps as django_apps
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from authentication.models import SisUser, User
from authentication.tokens import issue_tokens
from contact.models import Contact
from website.models import (
    FAQ, ContentBlock, MediaAsset, Page, ProgramCard, Project, Service, SiteSettings, SlugRedirect,
)

MEDIA_SETTINGS = {"MEDIA_ROOT": None}  # replaced per test run in setUpClass


def png_file(name="photo.png", size=(2400, 1200)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 120, 200)).save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class AdminAPITestBase(APITestCase):

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._media = tempfile.TemporaryDirectory()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media.name)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        cls._media.cleanup()

    def setUp(self):
        self.admin = SisUser.objects.create_user("admin", "admin@example.com", "Admin12345", choice="admin")
        self.employee = SisUser.objects.create_user("emp", "emp@example.com", "Employee123", choice="employee_role")
        self.editor = SisUser.objects.create_user("ed", "ed@example.com", "Editor12345", choice="editor")
        self.volunteer = User.objects.create(
            name="Riya Patil", email="riya@example.com", phone="9000000001", password="x",
            skills="Teaching, Design", location="Kolhapur", is_verified=True,
        )

    def login(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(user)['token']}")

    def logout(self):
        self.client.credentials()


# ---------------------------------------------------------------------------
# Roles and modules
# ---------------------------------------------------------------------------

class PermissionTests(AdminAPITestBase):

    def test_no_token_is_401(self):
        self.assertEqual(self.client.get("/api/admin/services/").status_code, 401)

    def test_volunteer_token_is_rejected(self):
        self.login(self.volunteer)
        self.assertEqual(self.client.get("/api/admin/services/").status_code, 401)

    def test_editor_gets_content_only(self):
        self.login(self.editor)
        self.assertEqual(self.client.get("/api/admin/services/").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/contacts/").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/volunteers/").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/staff/").status_code, 403)

    def test_employee_cannot_manage_staff(self):
        self.login(self.employee)
        self.assertEqual(self.client.get("/api/admin/contacts/").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/staff/").status_code, 403)

    def test_module_access_overrides_role(self):
        self.employee.module_access = ["inbox"]
        self.employee.save()
        self.login(self.employee)
        self.assertEqual(self.client.get("/api/admin/contacts/").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/services/").status_code, 403)

    def test_standard_pagination_shape(self):
        self.login(self.admin)
        data = self.client.get("/api/admin/services/").json()
        self.assertEqual(set(data), {"count", "next", "previous", "results"})


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

class ServiceTests(AdminAPITestBase):

    def create_service(self, **extra):
        self.login(self.admin)
        body = {
            "title": "Education & Child Welfare",
            "short_description": "Learning support for children.",
            "icon": "book",
            "activities": ["Tutoring", "Books, bags and uniforms"],
            "beneficiaries": ["Children 6-14"],
            **extra,
        }
        res = self.client.post("/api/admin/services/", body, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def test_create_makes_slug_and_starts_as_draft(self):
        service = self.create_service()
        self.assertEqual(service["slug"], "education-child-welfare")
        self.assertFalse(service["is_published"])
        self.assertEqual(service["activities"][1], "Books, bags and uniforms")
        self.assertEqual(service["updated_by_name"], "admin")

    def test_lists_must_be_json_arrays(self):
        self.login(self.admin)
        res = self.client.post("/api/admin/services/", {"title": "X", "activities": "a, b"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("activities", res.json())

    def test_drafts_never_reach_the_website(self):
        service = self.create_service()
        self.logout()
        self.assertEqual(self.client.get("/api/website/services/").json()["count"], 0)
        self.assertEqual(self.client.get(f"/api/website/services/{service['slug']}/").status_code, 404)

        self.login(self.admin)
        self.client.post(f"/api/admin/services/{service['id']}/publish/")
        self.logout()
        self.assertEqual(self.client.get("/api/website/services/").json()["count"], 1)
        self.assertEqual(self.client.get(f"/api/website/services/{service['slug']}/").status_code, 200)

    def test_public_endpoints_ignore_stale_tokens(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer expired-or-garbage")
        self.assertEqual(self.client.get("/api/website/services/").status_code, 200)

    def test_preview_link_shows_draft(self):
        service = self.create_service()
        link = self.client.post(f"/api/admin/services/{service['id']}/preview/").json()
        self.logout()
        res = self.client.get(f"/api/website/services/{service['slug']}/", {"preview": link["token"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["is_published"], False)
        bad = self.client.get(f"/api/website/services/{service['slug']}/", {"preview": "nope"})
        self.assertEqual(bad.status_code, 403)

    def test_slug_change_keeps_redirect(self):
        service = self.create_service(is_published=True)
        self.client.patch(f"/api/admin/services/{service['id']}/", {"slug": "education"}, format="json")
        self.logout()
        res = self.client.get(f"/api/website/services/{service['slug']}/")
        self.assertEqual(res.status_code, 301)
        self.assertEqual(res.json()["redirect_slug"], "education")
        self.assertEqual(self.client.get("/api/website/services/education/").status_code, 200)

    def test_reorder(self):
        a = self.create_service(title="A", is_published=True)
        b = self.create_service(title="B", is_published=True)
        res = self.client.post("/api/admin/services/reorder/", {"ids": [b["id"], a["id"]]}, format="json")
        self.assertEqual(res.status_code, 200)
        self.logout()
        titles = [s["title"] for s in self.client.get("/api/website/services/").json()["results"]]
        self.assertEqual(titles, ["B", "A"])

    def test_duplicate_is_a_draft_with_new_slug(self):
        service = self.create_service(is_published=True)
        res = self.client.post(f"/api/admin/services/{service['id']}/duplicate/")
        self.assertEqual(res.status_code, 201)
        copy = res.json()
        self.assertEqual(copy["title"], "Education & Child Welfare (copy)")
        self.assertNotEqual(copy["slug"], service["slug"])
        self.assertFalse(copy["is_published"])

    def test_delete_archives_first_then_deletes(self):
        service = self.create_service(is_published=True)
        url = f"/api/admin/services/{service['id']}/"
        self.assertTrue(self.client.delete(url).json()["archived"])
        obj = Service.objects.get(pk=service["id"])
        self.assertTrue(obj.is_archived)
        self.assertFalse(obj.is_published)
        self.assertEqual(self.client.get("/api/admin/services/").json()["count"], 0)
        self.assertEqual(self.client.get("/api/admin/services/?archived=true").json()["count"], 1)

        self.client.post(f"{url}restore/")
        self.assertFalse(Service.objects.get(pk=service["id"]).is_archived)

        self.client.delete(url)
        self.assertFalse(self.client.delete(url).json()["archived"])
        self.assertFalse(Service.objects.filter(pk=service["id"]).exists())

    def test_cannot_publish_archived(self):
        service = self.create_service()
        self.client.delete(f"/api/admin/services/{service['id']}/")
        res = self.client.post(f"/api/admin/services/{service['id']}/publish/")
        self.assertEqual(res.status_code, 400)

    def test_reserved_slug_is_avoided(self):
        service = self.create_service(title="Map")
        self.assertEqual(service["slug"], "map-2")


class ImageUploadTests(AdminAPITestBase):

    def setUp(self):
        super().setUp()
        self.service = Service.objects.create(title="Health")
        self.url = f"/api/admin/services/{self.service.pk}/image/"
        self.login(self.admin)

    def test_upload_keeps_original_and_webp_copy(self):
        res = self.client.post(self.url, {"image": png_file(), "alt": "Health camp"}, format="multipart")
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["cover_image"].startswith("http://testserver/media/services/"))
        self.assertTrue(data["cover_image_web"].endswith(".webp"))
        self.assertEqual(data["cover_image_alt"], "Health camp")
        self.service.refresh_from_db()
        with Image.open(self.service.cover_image_web.path) as web:
            self.assertLessEqual(max(web.size), 1600)

    def test_alt_text_required(self):
        res = self.client.post(self.url, {"image": png_file()}, format="multipart")
        self.assertEqual(res.status_code, 400)
        self.assertIn("alt", res.json())

    def test_rejects_non_images(self):
        fake = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
        res = self.client.post(self.url, {"image": fake, "alt": "x"}, format="multipart")
        self.assertEqual(res.status_code, 400)

    @override_settings(MAX_IMAGE_UPLOAD_MB=0)
    def test_rejects_large_files(self):
        res = self.client.post(self.url, {"image": png_file(), "alt": "x"}, format="multipart")
        self.assertEqual(res.status_code, 400)
        self.assertIn("MB", str(res.json()))

    def test_reuse_from_media_library(self):
        res = self.client.post(
            "/api/admin/media/", {"file": png_file(), "alt": "Volunteers planting"}, format="multipart"
        )
        self.assertEqual(res.status_code, 201, res.content)
        asset = res.json()
        self.assertEqual(asset["width"], 2400)
        self.assertTrue(asset["file_web"].endswith(".webp"))

        res = self.client.post(self.url, {"media_id": asset["id"]}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["cover_image_alt"], "Volunteers planting")

    def test_remove_image(self):
        self.client.post(self.url, {"image": png_file(), "alt": "x"}, format="multipart")
        res = self.client.delete(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["cover_image"])


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectTests(AdminAPITestBase):

    def setUp(self):
        super().setUp()
        self.service = Service.objects.create(title="Water", is_published=True)
        self.login(self.admin)

    def create_project(self, **extra):
        body = {"title": "Clean Water Kolhapur", "service": self.service.pk, "status": "active", **extra}
        res = self.client.post("/api/admin/projects/", body, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def test_template_fills_default_phases_and_safeguards(self):
        res = self.client.post("/api/admin/projects/?template=default", {"title": "New"}, format="json")
        phases = [p["name"] for p in res.json()["phases"]]
        self.assertEqual(phases, ["Discover", "Deliver", "Review"])
        self.assertEqual(len(res.json()["safeguards"]), 3)

    def test_nested_rows_are_validated(self):
        bad = self.client.post(
            "/api/admin/projects/", {"title": "X", "indicators": [{"measurement_method": "Survey"}]},
            format="json",
        )
        self.assertEqual(bad.status_code, 400)
        good = self.create_project(indicators=[
            {"area": "Health", "measurement_method": "Survey", "evidence_source": "Clinic records"}
        ])
        self.assertEqual(good["indicators"][0]["evidence_source"], "Clinic records")

    def test_featured_limit_is_three(self):
        for i in range(3):
            self.create_project(title=f"P{i}", is_featured=True)
        res = self.client.post("/api/admin/projects/", {"title": "P4", "is_featured": True}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("is_featured", res.json())

    def test_featured_order_and_public_filter(self):
        a = self.create_project(title="A", is_published=True)
        b = self.create_project(title="B", is_published=True)
        res = self.client.post("/api/admin/projects/featured-order/", {"ids": [b["id"], a["id"]]}, format="json")
        self.assertEqual(res.status_code, 200)
        self.logout()
        titles = [p["title"] for p in self.client.get("/api/website/projects/?featured=true").json()["results"]]
        self.assertEqual(titles, ["B", "A"])

    def test_public_filters_by_service_slug(self):
        self.create_project(is_published=True)
        other = Service.objects.create(title="Health", is_published=True)
        self.create_project(title="Health camp", service=other.pk, is_published=True)
        self.logout()
        res = self.client.get(f"/api/website/projects/?service={self.service.slug}").json()
        self.assertEqual([p["title"] for p in res["results"]], ["Clean Water Kolhapur"])
        self.assertEqual(res["results"][0]["service"]["slug"], "water")

    def test_map_pins(self):
        self.create_project(title="Shown", is_published=True, latitude="16.7050", longitude="74.2433")
        self.create_project(title="Hidden", is_published=True, latitude="18.5", longitude="73.8", show_on_map=False)
        self.create_project(title="No coords", is_published=True)
        self.logout()
        pins = self.client.get("/api/website/projects/map/").json()
        self.assertEqual([p["title"] for p in pins], ["Shown"])
        self.assertEqual(pins[0]["latitude"], "16.705000")

    def test_people_benefited_only_when_verified(self):
        project = self.create_project(is_published=True, people_benefited=420)
        self.logout()
        detail = self.client.get(f"/api/website/projects/{project['slug']}/").json()
        self.assertIsNone(detail["people_benefited"])
        Project.objects.filter(pk=project["id"]).update(people_benefited_verified=True)
        detail = self.client.get(f"/api/website/projects/{project['slug']}/").json()
        self.assertEqual(detail["people_benefited"], 420)

    def test_gallery_add_and_remove(self):
        project = self.create_project()
        url = f"/api/admin/projects/{project['id']}/gallery/"
        res = self.client.post(url, {"image": png_file(), "alt": "Well"}, format="multipart")
        self.assertEqual(res.status_code, 201, res.content)
        image_id = res.json()["id"]
        self.assertEqual(len(self.client.get(f"/api/admin/projects/{project['id']}/").json()["gallery"]), 1)
        self.assertEqual(self.client.delete(f"{url}{image_id}/").status_code, 200)
        self.assertEqual(self.client.delete(f"{url}{image_id}/").status_code, 404)

    def test_match_volunteers(self):
        project = self.create_project(location_name="Kolhapur, Maharashtra")
        url = f"/api/admin/projects/{project['id']}/"
        suggested = self.client.get(f"{url}suggested-volunteers/?skills=teaching").json()
        self.assertEqual([v["id"] for v in suggested], [self.volunteer.pk])

        res = self.client.post(f"{url}volunteers/", {"volunteer_ids": [self.volunteer.pk]}, format="json")
        self.assertEqual(len(res.json()), 1)
        self.assertEqual(self.client.get(f"{url}suggested-volunteers/?skills=teaching").json(), [])

        self.login(self.editor)
        self.assertEqual(self.client.get(f"{url}volunteers/").status_code, 403)

    def test_end_before_start_rejected(self):
        res = self.client.post(
            "/api/admin/projects/", {"title": "X", "start_date": "2026-05-01", "end_date": "2026-04-01"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)


# ---------------------------------------------------------------------------
# Other content
# ---------------------------------------------------------------------------

class OtherContentTests(AdminAPITestBase):

    def setUp(self):
        super().setUp()
        self.login(self.editor)

    def test_impact_create_and_latest_by_date(self):
        for day, children in (("2026-01-01", 100), ("2026-06-01", 250)):
            res = self.client.post("/api/admin/impact/", {
                "children_women_supported": children, "skill_awareness_programs": 4,
                "communities_reached": 9, "date": day,
            }, format="json")
            self.assertEqual(res.status_code, 201, res.content)
        self.logout()
        latest = self.client.get("/api/website/our-impact/latest/").json()
        self.assertEqual(latest["children_women_supported"], 250)

    def test_leadership_crud_and_hidden(self):
        res = self.client.post("/api/admin/leadership/", {
            "name": "A. Kulkarni", "position": "Founder", "short_description": "Bio",
        }, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        leader = res.json()
        self.client.post(f"/api/admin/leadership/{leader['id']}/unpublish/")
        self.logout()
        self.assertEqual(self.client.get("/api/website/leadership/").json(), [])

    def test_faqs(self):
        self.client.post("/api/admin/faqs/", {"question": "Q1?", "answer": "A1", "is_published": True}, format="json")
        self.client.post("/api/admin/faqs/", {"question": "Draft?", "answer": "A2"}, format="json")
        self.logout()
        res = self.client.get("/api/website/faqs/").json()
        self.assertEqual([f["question"] for f in res["results"]], ["Q1?"])

    def test_site_settings(self):
        res = self.client.patch("/api/admin/settings/", {
            "contact_email": "hello@example.org",
            "instagram_url": "https://instagram.com/qq",
            "donate_focus_areas": [{"title": "Education", "description": "Books"}],
        }, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        bad = self.client.patch("/api/admin/settings/", {"get_involved_options": ["x"]}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.logout()
        public = self.client.get("/api/website/settings/").json()
        self.assertEqual(public["contact_email"], "hello@example.org")
        self.assertEqual(public["donate_focus_areas"][0]["title"], "Education")
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_content_blocks(self):
        self.client.post("/api/admin/content-blocks/", {
            "key": "about.vision", "body": "A world where...", "is_published": True,
        }, format="json")
        self.client.post("/api/admin/content-blocks/", {
            "key": "about.objectives", "data": {"items": ["One", "Two"]}, "is_published": True,
        }, format="json")
        self.client.post("/api/admin/content-blocks/", {"key": "home.hero.headline", "is_published": True}, format="json")
        bad = self.client.post("/api/admin/content-blocks/", {"key": "Has Spaces"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.logout()
        res = self.client.get("/api/website/content-blocks/?prefix=about.").json()
        self.assertEqual(res["count"], 2)
        one = self.client.get("/api/website/content-blocks/about.vision/").json()
        self.assertEqual(one["body"], "A world where...")

    def test_pages(self):
        res = self.client.post("/api/admin/pages/", {
            "title": "Privacy Policy", "body": "<p>We respect your privacy.</p>", "is_published": True,
        }, format="json")
        self.assertEqual(res.json()["slug"], "privacy-policy")
        self.logout()
        page = self.client.get("/api/website/pages/privacy-policy/").json()
        self.assertIn("privacy", page["body"])

    def test_stats(self):
        User.objects.create(name="Unverified", email="u@example.com", password="x")
        Project.objects.create(title="P", is_published=True, people_benefited=50, people_benefited_verified=True)
        self.logout()
        stats = self.client.get("/api/website/stats/").json()
        self.assertEqual(stats["volunteers"], 1)
        self.assertEqual(stats["projects"], 1)
        self.assertEqual(stats["people_benefited"], 50)


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------

class InboxTests(AdminAPITestBase):

    def setUp(self):
        super().setUp()
        self.guest = Contact.objects.create(name="=HYPERLINK(1)", email="g@example.com", contact="1", address="Pune", message="Hi")
        self.member = Contact.objects.create(user=self.volunteer, message="I can help")
        self.login(self.employee)

    def test_list_filter_and_sender_details(self):
        res = self.client.get("/api/admin/contacts/?status=new").json()
        self.assertEqual(res["count"], 2)
        member = next(c for c in res["results"] if c["id"] == self.member.pk)
        self.assertEqual(member["sender_email"], "riya@example.com")
        self.assertTrue(member["is_registered"])

    def test_assign_status_and_notes(self):
        url = f"/api/admin/contacts/{self.guest.pk}/"
        res = self.client.patch(url, {"assigned_to": self.employee.pk}, format="json")
        self.assertEqual(res.json()["assigned_to_name"], "emp")
        note = self.client.post(f"{url}notes/", {"text": "Called back"}, format="json")
        self.assertEqual(note.status_code, 201)
        self.assertEqual(self.client.get(url).json()["status"], "in_progress")
        self.client.patch(url, {"status": "replied"}, format="json")
        mine = self.client.get("/api/admin/contacts/?assigned_to=me&status=replied").json()
        self.assertEqual(mine["count"], 1)

    def test_cannot_assign_to_editor(self):
        res = self.client.patch(f"/api/admin/contacts/{self.guest.pk}/", {"assigned_to": self.editor.pk}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_message_text_is_read_only(self):
        self.client.patch(f"/api/admin/contacts/{self.guest.pk}/", {"message": "changed"}, format="json")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.message, "Hi")

    def test_export_csv_escapes_formulas(self):
        res = self.client.get("/api/admin/contacts/export/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res["Content-Type"].startswith("text/csv"))
        body = res.content.decode("utf-8-sig")
        self.assertIn("'=HYPERLINK(1)", body)


# ---------------------------------------------------------------------------
# Volunteers
# ---------------------------------------------------------------------------

class VolunteerToolTests(AdminAPITestBase):

    def setUp(self):
        super().setUp()
        self.other = User.objects.create(name="Amit", email="amit@example.com", password="x",
                                         skills="Accounting", location="Pune", is_verified=False)
        self.login(self.employee)

    def test_filters(self):
        res = self.client.get("/api/admin/volunteers/?skills=teach").json()
        self.assertEqual([v["id"] for v in res["results"]], [self.volunteer.pk])
        res = self.client.get("/api/admin/volunteers/?is_verified=false").json()
        self.assertEqual([v["id"] for v in res["results"]], [self.other.pk])
        self.assertNotIn("password", res["results"][0])
        self.assertNotIn("otp", res["results"][0])

    def test_deactivate_blocks_login_and_tokens(self):
        volunteer_token = issue_tokens(self.volunteer)["token"]
        res = self.client.delete(f"/api/admin/volunteers/{self.volunteer.pk}/")
        self.assertFalse(res.json()["is_active"])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {volunteer_token}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

        self.login(self.employee)
        self.client.post(f"/api/admin/volunteers/{self.volunteer.pk}/activate/")
        self.volunteer.refresh_from_db()
        self.assertTrue(self.volunteer.is_active)

    def test_resend_verification(self):
        res = self.client.post(f"/api/admin/volunteers/{self.other.pk}/resend-verification/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        res = self.client.post(f"/api/admin/volunteers/{self.volunteer.pk}/resend-verification/")
        self.assertEqual(res.status_code, 400)

    def test_export(self):
        res = self.client.get("/api/admin/volunteers/export/?location=pune")
        body = res.content.decode("utf-8-sig").splitlines()
        self.assertEqual(len(body), 2)
        self.assertIn("amit@example.com", body[1])


# ---------------------------------------------------------------------------
# Staff accounts and security
# ---------------------------------------------------------------------------

class StaffSecurityTests(AdminAPITestBase):

    def staff_login(self, username, password):
        self.logout()
        return self.client.post("/api/auth/sisuser/login/", {"username": username, "password": password})

    def test_admin_creates_editor_with_modules(self):
        self.login(self.admin)
        res = self.client.post("/api/admin/staff/", {
            "username": "writer", "email": "w@example.com", "password": "Writer1234",
            "choice": "editor", "module_access": ["content"],
        }, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["modules"], ["content"])
        self.assertNotIn("password", res.json())
        login = self.staff_login("writer", "Writer1234").json()
        self.assertEqual(login["modules"], ["content"])
        self.assertIn("refresh", login)

    def test_module_access_is_optional_and_nullable(self):
        self.login(self.admin)
        base = {"password": "Staffer1234", "choice": "employee_role"}
        omitted = self.client.post("/api/admin/staff/", {**base, "username": "s1", "email": "s1@example.com"}, format="json")
        self.assertEqual(omitted.status_code, 201, omitted.content)
        self.assertEqual(omitted.json()["module_access"], [])
        self.assertEqual(omitted.json()["modules"], ["campaigns", "content", "inbox", "volunteers"])

        null = self.client.post("/api/admin/staff/", {**base, "username": "s2", "email": "s2@example.com",
                                                      "module_access": None}, format="json")
        self.assertEqual(null.status_code, 201, null.content)
        self.assertEqual(null.json()["module_access"], [])

        url = f"/api/admin/staff/{null.json()['id']}/"
        narrowed = self.client.patch(url, {"module_access": ["inbox"]}, format="json")
        self.assertEqual(narrowed.json()["modules"], ["inbox"])
        cleared = self.client.patch(url, {"module_access": None}, format="json")
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertEqual(cleared.json()["modules"], ["campaigns", "content", "inbox", "volunteers"])

        bad = self.client.patch(url, {"module_access": ["everything"]}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_admin_cannot_deactivate_self_or_drop_own_role(self):
        self.login(self.admin)
        self.assertEqual(self.client.delete(f"/api/admin/staff/{self.admin.pk}/").status_code, 400)
        res = self.client.patch(f"/api/admin/staff/{self.admin.pk}/", {"choice": "editor"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_deactivated_staff_cannot_log_in(self):
        self.login(self.admin)
        self.client.delete(f"/api/admin/staff/{self.employee.pk}/")
        self.assertEqual(self.staff_login("emp", "Employee123").status_code, 403)

    def test_lockout_after_repeated_failures(self):
        for _ in range(SisUser.MAX_FAILED_LOGINS):
            self.assertEqual(self.staff_login("emp", "wrong").status_code, 401)
        res = self.staff_login("emp", "Employee123")
        self.assertEqual(res.status_code, 403)
        self.assertIn("Too many failed attempts", res.json()["Error"])

        self.login(self.admin)
        self.client.post(f"/api/admin/staff/{self.employee.pk}/unlock/")
        self.assertEqual(self.staff_login("emp", "Employee123").status_code, 200)

    def test_lock_expires(self):
        self.employee.locked_until = timezone.now() - timedelta(minutes=1)
        self.employee.save()
        self.assertEqual(self.staff_login("emp", "Employee123").status_code, 200)

    def test_reset_password_logs_out_old_sessions(self):
        old = issue_tokens(self.employee)["token"]
        self.login(self.admin)
        res = self.client.post(f"/api/admin/staff/{self.employee.pk}/reset-password/",
                               {"new_password": "BrandNew123"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old}")
        self.assertEqual(self.client.get("/api/auth/profile/").status_code, 401)
        self.assertEqual(self.staff_login("emp", "BrandNew123").status_code, 200)

    def test_change_own_password(self):
        self.login(self.employee)
        bad = self.client.post("/api/auth/sisuser/change-password/",
                               {"old_password": "nope", "new_password": "Another123"}, format="json")
        self.assertEqual(bad.status_code, 400)
        res = self.client.post("/api/auth/sisuser/change-password/",
                               {"old_password": "Employee123", "new_password": "Another123"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.json()['token']}")
        self.assertEqual(self.client.get("/api/auth/profile/").status_code, 200)


# ---------------------------------------------------------------------------
# Auth gaps: refresh, me, resend OTP
# ---------------------------------------------------------------------------

class AuthGapTests(AdminAPITestBase):

    def test_refresh_flow(self):
        tokens = issue_tokens(self.volunteer)
        res = self.client.post("/api/auth/token/refresh/", {"refresh": tokens["refresh"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(set(res.json()), {"token", "refresh"})
        # An access token is not a refresh token, and vice versa.
        self.assertEqual(self.client.post("/api/auth/token/refresh/", {"refresh": tokens["token"]}).status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['refresh']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_volunteer_login_includes_id(self):
        self.volunteer.password = "pbkdf2_sha256$placeholder"
        from django.contrib.auth.hashers import make_password
        self.volunteer.password = make_password("Secret123")
        self.volunteer.save()
        res = self.client.post("/api/auth/login/", {"email": "riya@example.com", "password": "Secret123"}).json()
        self.assertEqual(res["user"]["id"], self.volunteer.pk)
        self.assertEqual(res["user"]["volunteer_id"], self.volunteer.volunteer_id)
        self.assertIn("refresh", res)

    def test_me_get_and_patch(self):
        self.login(self.volunteer)
        self.assertEqual(self.client.get("/api/auth/me/").json()["volunteer_id"], self.volunteer.volunteer_id)
        res = self.client.patch("/api/auth/me/", {"location": "Pune", "email": "hijack@example.com"}, format="json")
        self.assertEqual(res.json()["location"], "Pune")
        self.assertEqual(res.json()["email"], "riya@example.com")
        self.login(self.admin)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_resend_otp_with_cooldown(self):
        pending = User.objects.create(name="New", email="new@example.com", password="x")
        res = self.client.post("/api/auth/resend-otp/", {"email": "new@example.com"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        pending.refresh_from_db()
        self.assertIn(pending.otp, mail.outbox[0].body)
        self.assertEqual(self.client.post("/api/auth/resend-otp/", {"email": "new@example.com"}).status_code, 429)
        self.assertEqual(self.client.post("/api/auth/resend-otp/", {"email": "riya@example.com"}).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/resend-otp/", {"email": "none@example.com"}).status_code, 404)


# ---------------------------------------------------------------------------
# Dashboard, campaigns, refresh hook, data migration
# ---------------------------------------------------------------------------

class DashboardAndCampaignTests(AdminAPITestBase):

    def test_dashboard_home(self):
        Contact.objects.create(name="G", email="g@example.com", message="Hi")
        Project.objects.create(title="Live", is_published=True)
        self.login(self.editor)
        data = self.client.get("/api/admin/dashboard/").json()
        self.assertEqual(data["volunteers"]["total"], 1)
        self.assertEqual(data["messages"]["unread"], 1)
        self.assertEqual(data["content"]["published_projects"], 1)
        self.assertTrue(any(a["type"] == "message_received" for a in data["recent_activity"]))


    def test_donation_requires_donor(self):
        self.login(self.admin)
        self.assertEqual(self.client.post("/api/admin/donations/", {"amount": "10.00"}, format="json").status_code, 400)
        res = self.client.post("/api/admin/donations/", {"amount": "10.00", "donor": self.volunteer.pk}, format="json")
        self.assertEqual(res.status_code, 201)


class _InlineThread:
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class RevalidateHookTests(AdminAPITestBase):

    @override_settings(WEBSITE_REVALIDATE_URL="https://site.test/api/revalidate", WEBSITE_REVALIDATE_SECRET="s3cret")
    def test_content_save_calls_hook(self):
        with patch("website.revalidate.threading.Thread", _InlineThread), \
                patch("website.revalidate.urllib.request.urlopen") as urlopen, \
                self.captureOnCommitCallbacks(execute=True):
            FAQ.objects.create(question="Q", answer="A")
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://site.test/api/revalidate")
        self.assertEqual(request.get_header("X-revalidate-secret"), "s3cret")

    def test_no_url_no_call(self):
        with patch("website.revalidate.urllib.request.urlopen") as urlopen, \
                self.captureOnCommitCallbacks(execute=True):
            FAQ.objects.create(question="Q", answer="A")
        urlopen.assert_not_called()


class ProgramCardMigrationTests(APITestCase):

    def test_cards_become_services(self):
        ProgramCard.objects.create(
            icon="heart", title="Health", description="Camps",
            activities="Key Activities:", activity_points="Check-ups, Medicines, ",
            target="Target Beneficiaries:", benefits="Women,Children",
        )
        migration = importlib.import_module("website.migrations.0005_programcards_to_services")
        migration.forwards(django_apps, None)
        service = Service.objects.get()
        self.assertEqual(service.activities, ["Check-ups", "Medicines"])
        self.assertEqual(service.beneficiaries, ["Women", "Children"])
        self.assertEqual(service.activities_heading, "Key Activities")
        self.assertEqual(service.icon, "heart")
        self.assertTrue(service.is_published)


# ---------------------------------------------------------------------------
# Campaigns (spec part 2)
# ---------------------------------------------------------------------------

from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from dashboard.models import Campaign, CampaignVolunteer, Donation


class CampaignTests(AdminAPITestBase):

    def setUp(self):
        super().setUp()
        self.service = Service.objects.create(title="Water", is_published=True)
        self.other_volunteer = User.objects.create(name="Amit", email="amit@example.com", password="x", is_verified=True)

    def create_campaign(self, **extra):
        self.login(self.employee)
        body = {"title": "Clean Water Drive", "summary": "Wells for Kolhapur", "service": self.service.pk, **extra}
        res = self.client.post("/api/admin/campaigns/", body, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def test_create_defaults(self):
        campaign = self.create_campaign()
        self.assertEqual(campaign["slug"], "clean-water-drive")
        self.assertEqual(campaign["status"], "upcoming")
        self.assertFalse(campaign["is_published"])
        self.assertEqual(campaign["raised_amount"], "0.00")
        self.assertEqual(campaign["service_title"], "Water")
        self.assertEqual(campaign["updated_by_name"], "emp")

    def test_validation(self):
        self.login(self.employee)
        bad_dates = self.client.post("/api/admin/campaigns/", {
            "title": "X", "start_date": "2026-12-10", "end_date": "2026-12-01",
        }, format="json")
        self.assertEqual(bad_dates.status_code, 400)
        self.assertIn("end_date", bad_dates.json())
        bad_goal = self.client.post("/api/admin/campaigns/", {"title": "X", "goal_amount": "-5"}, format="json")
        self.assertEqual(bad_goal.status_code, 400)

    def test_editor_has_no_campaigns_module(self):
        self.login(self.editor)
        self.assertEqual(self.client.get("/api/admin/campaigns/").status_code, 403)

    def test_edit_archive_restore_delete(self):
        campaign = self.create_campaign()
        url = f"/api/admin/campaigns/{campaign['id']}/"
        res = self.client.patch(url, {"status": "active"}, format="json")
        self.assertEqual(res.json()["status"], "active")
        self.assertTrue(self.client.delete(url).json()["archived"])
        self.client.post(f"{url}restore/")
        self.client.delete(url)
        self.assertFalse(self.client.delete(url).json()["archived"])
        self.assertFalse(Campaign.objects.filter(pk=campaign["id"]).exists())

    def test_publish_and_public_filters(self):
        live = self.create_campaign(status="active", is_published=True, is_featured=True)
        self.create_campaign(title="Old one", status="completed", is_published=True)
        self.create_campaign(title="Draft", status="active")
        self.logout()
        res = self.client.get("/api/website/campaigns/").json()
        self.assertEqual(res["count"], 2)
        self.assertEqual(
            [c["slug"] for c in self.client.get("/api/website/campaigns/?status=active").json()["results"]],
            [live["slug"]],
        )
        self.assertEqual(self.client.get("/api/website/campaigns/?featured=true").json()["count"], 1)
        self.assertEqual(self.client.get("/api/website/campaigns/?service=water").json()["count"], 2)
        self.assertEqual(self.client.get(f"/api/website/campaigns/?service={self.service.pk}").json()["count"], 2)
        self.assertEqual(self.client.get("/api/website/campaigns/draft/").status_code, 404)

    def test_stats_are_not_multiplied(self):
        campaign = self.create_campaign(status="active", is_published=True, goal_amount="350.00")
        obj = Campaign.objects.get(pk=campaign["id"])
        Donation.objects.create(donor=self.volunteer, amount=Decimal("100"), campaign=obj)
        Donation.objects.create(donor=self.volunteer, amount=Decimal("50"), campaign=obj)
        Donation.objects.create(donor=self.other_volunteer, amount=Decimal("25"), campaign=obj)
        Donation.objects.create(donor=self.other_volunteer, amount=Decimal("999"))  # not linked
        CampaignVolunteer.objects.create(campaign=obj, volunteer=self.volunteer)
        CampaignVolunteer.objects.create(campaign=obj, volunteer=self.other_volunteer)

        for url in ("/api/admin/campaigns/", "/api/website/campaigns/"):
            if url.startswith("/api/website"):
                self.logout()
            item = self.client.get(url).json()["results"][0]
            self.assertEqual(item["raised_amount"], "175.00")
            self.assertEqual(item["donor_count"], 2)
            self.assertEqual(item["volunteer_count"], 2)
            self.assertEqual(item["progress_percent"], 50)

    def test_volunteer_fields_on_public_list(self):
        campaign = self.create_campaign(status="active", is_published=True)
        obj = Campaign.objects.get(pk=campaign["id"])
        Donation.objects.create(donor=self.volunteer, amount=Decimal("40"), campaign=obj)

        self.logout()
        anonymous = self.client.get(f"/api/website/campaigns/{obj.slug}/").json()
        self.assertIsNone(anonymous["has_joined"])
        self.assertIsNone(anonymous["my_donation_total"])

        self.client.credentials(HTTP_AUTHORIZATION="Bearer stale-token")
        self.assertEqual(self.client.get("/api/website/campaigns/").status_code, 200)

        self.login(self.volunteer)
        mine = self.client.get("/api/website/campaigns/").json()["results"][0]
        self.assertFalse(mine["has_joined"])
        self.assertEqual(mine["my_donation_total"], "40.00")

    def test_join_and_leave(self):
        campaign = self.create_campaign(status="active", is_published=True)
        url = f"/api/campaigns/{campaign['id']}/join/"

        self.logout()
        self.assertEqual(self.client.post(url).status_code, 401)
        self.login(self.admin)
        self.assertEqual(self.client.post(url).status_code, 401)

        self.login(self.volunteer)
        res = self.client.post(url)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["volunteer_count"], 1)
        self.assertEqual(self.client.post(url).status_code, 200)
        detail = self.client.get(f"/api/website/campaigns/{campaign['slug']}/").json()
        self.assertTrue(detail["has_joined"])

        res = self.client.delete(url)
        self.assertFalse(res.json()["has_joined"])
        self.assertEqual(CampaignVolunteer.objects.count(), 0)

    def test_join_rules(self):
        closed = self.create_campaign(title="No volunteers", is_published=True, status="active", allow_volunteers=False)
        ended = self.create_campaign(title="Ended", is_published=True, status="completed")
        draft = self.create_campaign(title="Draft", status="active")
        self.login(self.volunteer)
        self.assertEqual(self.client.post(f"/api/campaigns/{closed['id']}/join/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/campaigns/{ended['id']}/join/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/campaigns/{draft['id']}/join/").status_code, 404)

    def test_my_campaigns(self):
        joined = self.create_campaign(title="Joined", status="active", is_published=True)
        self.create_campaign(title="Not joined", status="active", is_published=True)
        obj = Campaign.objects.get(pk=joined["id"])
        Donation.objects.create(donor=self.volunteer, amount=Decimal("75"), campaign=obj)
        self.login(self.volunteer)
        self.client.post(f"/api/campaigns/{joined['id']}/join/")
        res = self.client.get("/api/auth/me/campaigns/").json()
        self.assertEqual(res["count"], 1)
        item = res["results"][0]
        self.assertEqual(item["title"], "Joined")
        self.assertEqual(item["my_donation_total"], "75.00")
        self.assertIsNotNone(item["joined_at"])
        self.assertTrue(item["has_joined"])

    def test_admin_volunteer_list_and_export(self):
        campaign = self.create_campaign(status="active", is_published=True)
        obj = Campaign.objects.get(pk=campaign["id"])
        CampaignVolunteer.objects.create(campaign=obj, volunteer=self.volunteer)
        self.login(self.employee)
        res = self.client.get(f"/api/admin/campaigns/{obj.pk}/volunteers/").json()
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["results"][0]["email"], "riya@example.com")
        export = self.client.get(f"/api/admin/campaigns/{obj.pk}/volunteers/export/")
        self.assertTrue(export["Content-Type"].startswith("text/csv"))
        self.assertIn("riya@example.com", export.content.decode("utf-8-sig"))

    def test_donations_link_to_campaign(self):
        campaign = self.create_campaign(status="active", is_published=True)
        self.login(self.admin)
        res = self.client.post("/api/admin/donations/", {
            "donor": self.volunteer.pk, "amount": "20.00", "campaign": campaign["id"],
        }, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["campaign_title"], "Clean Water Drive")
        self.client.post("/api/admin/donations/", {"donor": self.volunteer.pk, "amount": "5.00"}, format="json")
        self.assertEqual(self.client.get(f"/api/admin/donations/?campaign={campaign['id']}").json()["count"], 1)
        self.assertEqual(self.client.get("/api/admin/donations/?campaign=none").json()["count"], 1)

    def test_volunteer_cannot_donate_to_draft_campaign(self):
        draft = self.create_campaign(title="Draft")
        self.login(self.volunteer)
        res = self.client.post("/api/dashboard/donations/", {"amount": "10.00", "campaign": draft["id"]})
        self.assertEqual(res.status_code, 400)

    def test_preview_redirect_duplicate_image(self):
        campaign = self.create_campaign(status="active")
        url = f"/api/admin/campaigns/{campaign['id']}/"
        token = self.client.post(f"{url}preview/").json()["token"]
        res = self.client.post(f"{url}image/", {"image": png_file(), "alt": "Volunteers at a well"}, format="multipart")
        self.assertTrue(res.json()["cover_image_web"].endswith(".webp"))
        copy = self.client.post(f"{url}duplicate/").json()
        self.assertEqual(copy["title"], "Clean Water Drive (copy)")

        self.client.post(f"{url}publish/")
        self.client.patch(url, {"slug": "water-drive"}, format="json")
        self.logout()
        self.assertEqual(
            self.client.get(f"/api/website/campaigns/{campaign['slug']}/").json()["redirect_slug"], "water-drive"
        )
        draft_view = self.client.get(f"/api/website/campaigns/water-drive/?preview={token}")
        self.assertEqual(draft_view.status_code, 200)

    def test_reorder(self):
        a = self.create_campaign(title="A", is_published=True)
        b = self.create_campaign(title="B", is_published=True)
        self.client.post("/api/admin/campaigns/reorder/", {"ids": [b["id"], a["id"]]}, format="json")
        self.logout()
        titles = [c["title"] for c in self.client.get("/api/website/campaigns/").json()["results"]]
        self.assertEqual(titles, ["B", "A"])

    @override_settings(WEBSITE_REVALIDATE_URL="https://site.test/revalidate")
    def test_donation_refreshes_campaign_page(self):
        campaign = Campaign.objects.create(title="Drive", is_published=True)
        with patch("website.revalidate.threading.Thread", _InlineThread), \
                patch("website.revalidate.urllib.request.urlopen") as urlopen, \
                self.captureOnCommitCallbacks(execute=True):
            Donation.objects.create(donor=self.volunteer, amount=Decimal("10"), campaign=campaign)
        body = urlopen.call_args[0][0].data
        self.assertIn(b'"model": "campaign"', body)
        self.assertIn(b'"slug": "drive"', body)


class CampaignMigrationTests(TransactionTestCase):
    """Existing campaigns keep showing after the upgrade, with a slug and a status."""

    before = [("dashboard", "0005_initial")]
    after = [("dashboard", "0007_campaign_public_fields")]

    def test_existing_campaigns_are_upgraded(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old_apps = executor.loader.project_state(self.before).apps
        OldCampaign = old_apps.get_model("dashboard", "Campaign")
        OldCampaign.objects.create(title="Water Drive", description="d", is_active=True)
        OldCampaign.objects.create(title="Water Drive", description="d", is_active=False)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.after)
        new_apps = executor.loader.project_state(self.after).apps
        NewCampaign = new_apps.get_model("dashboard", "Campaign")
        rows = list(NewCampaign.objects.order_by("id").values("slug", "status", "is_published"))
        self.assertEqual(rows, [
            {"slug": "water-drive", "status": "active", "is_published": True},
            {"slug": "water-drive-2", "status": "completed", "is_published": True},
        ])

        # Leave the database fully migrated for the tests that follow.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
