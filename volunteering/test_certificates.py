import datetime
import io
from decimal import Decimal

import segno
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.exceptions import ValidationError

from adminpanel.tests import AdminAPITestBase, png_file
from authentication.models import User
from website.models import Project, ProjectVolunteer

from . import certificates as drawing
from .models import Attendance, Certificate


def template_upload(size=(1600, 1100), name="template.png"):
    buffer = io.BytesIO()
    Image.new("RGB", size, (250, 248, 240)).save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class CertificateTestBase(AdminAPITestBase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.project = Project.objects.create(
            title="Clean Water Kolhapur", status="active", is_published=True,
            certificates_enabled=True, end_date=datetime.date(2026, 11, 22),
        )
        self.other = User.objects.create(name="Amit Shah", email="amit@example.com", password="x", is_verified=True)
        # Riya attended twice, Amit only has a pending photo.
        for days_ago in (1, 3):
            Attendance.objects.create(project=self.project, volunteer=self.volunteer, method="code", status="approved",
                                      date=datetime.date(2026, 11, 22) - datetime.timedelta(days=days_ago))
        Attendance.objects.create(project=self.project, volunteer=self.other, method="photo", status="pending")
        ProjectVolunteer.objects.create(project=self.project, volunteer=self.volunteer, joined_by="self")

    def issue(self, **body):
        self.login(self.employee)
        return self.client.post(f"/api/admin/projects/{self.project.pk}/certificates/issue/", body, format="json")


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

class RenderingTests(AdminAPITestBase):

    def render(self, **layout):
        return drawing.render(drawing.DEFAULT_TEMPLATE.read_bytes(), name="Riya Patil", project="Clean Water",
                              date=datetime.date(2026, 11, 22), certificate_id="QQ-7K3P-9XRM", layout=layout)

    def test_qr_code_reads_back_as_the_verify_link(self):
        image = self.render().convert("L")
        width, height = image.size
        spec = drawing.DEFAULT_LAYOUT["qr"]
        side = round(spec["size"] * height)
        rows = list(segno.make(drawing.verify_url("QQ-7K3P-9XRM"), error="m").matrix_iter(scale=1, border=1))
        left, top, module = round(spec["x"] * width), round(spec["y"] * height), side / len(rows)
        for j, row in enumerate(rows):
            for i, dark in enumerate(row):
                pixel = image.getpixel((int(left + (i + 0.5) * module), int(top + (j + 0.5) * module)))
                self.assertEqual(pixel < 128, bool(dark), f"module {i},{j}")

    def test_verify_link(self):
        self.assertEqual(drawing.verify_url("QQ-7K3P-9XRM"),
                         "https://quenchquestsocialfoundation.org/verify?id=QQ-7K3P-9XRM")

    def test_text_is_drawn_and_fits(self):
        blank = Image.open(drawing.DEFAULT_TEMPLATE).convert("RGB")
        long_name = drawing.render(drawing.DEFAULT_TEMPLATE.read_bytes(), name="A" * 90, project="P",
                                   date=datetime.date(2026, 1, 1), certificate_id="QQ-AAAA-AAAA")
        w, h = blank.size
        name_band = (0, int(0.38 * h), w, int(0.46 * h))
        self.assertNotEqual(blank.crop(name_band).tobytes(), long_name.crop(name_band).tobytes())
        # Shrunk to the line: nothing drawn outside the middle half of the page in that band.
        spec = drawing.DEFAULT_LAYOUT["name"]
        margin = int((spec["x"] - spec["max_width"] / 2) * w) - 2
        self.assertEqual(blank.crop((0, *name_band[1:2], margin, name_band[3])).tobytes(),
                         long_name.crop((0, *name_band[1:2], margin, name_band[3])).tobytes())

    def test_date_format(self):
        self.assertEqual(drawing.format_date(datetime.date(2026, 11, 2)), "2 November 2026")

    def test_layout_validation(self):
        self.assertEqual(drawing.validate_layout({"name": {"y": 0.5, "color": "#000000"}}),
                         {"name": {"y": 0.5, "color": "#000000"}})
        for bad in ({"logo": {}}, {"name": {"y": 2}}, {"name": {"color": "red"}}, {"qr": {"align": "left"}},
                    {"name": {"bold": "yes"}}, "oops"):
            with self.assertRaises(ValidationError, msg=bad):
                drawing.validate_layout(bad)

    def test_pdf(self):
        self.assertTrue(drawing.to_pdf(self.render()).startswith(b"%PDF"))


# ---------------------------------------------------------------------------
# Project settings, template, preview
# ---------------------------------------------------------------------------

class CertificateSettingsTests(CertificateTestBase):

    def url(self, part):
        return f"/api/admin/projects/{self.project.pk}/{part}/"

    def test_settings(self):
        self.login(self.employee)
        data = self.client.get(self.url("certificate-settings")).json()
        self.assertTrue(data["certificates_enabled"])
        self.assertTrue(data["uses_default_template"])
        self.assertIn("qr", data["default_layout"])

        res = self.client.patch(self.url("certificate-settings"), {
            "certificates_enabled": False, "certificate_layout": {"name": {"y": 0.44}},
        }, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.project.refresh_from_db()
        self.assertFalse(self.project.certificates_enabled)
        self.assertEqual(self.project.certificate_layout, {"name": {"y": 0.44}})

        bad = self.client.patch(self.url("certificate-settings"), {"certificate_layout": {"name": {"y": 9}}}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_project_form_yes_no(self):
        self.login(self.editor)
        res = self.client.patch(f"/api/admin/projects/{self.project.pk}/", {
            "certificates_enabled": False, "certificate_layout": {"name": {"y": 99}},
        }, format="json")
        self.assertEqual(res.status_code, 200)
        self.project.refresh_from_db()
        self.assertFalse(self.project.certificates_enabled)
        self.assertEqual(self.project.certificate_layout, {})  # read-only there; validated endpoint only

    def test_editor_cannot_manage_certificates(self):
        self.login(self.editor)
        self.assertEqual(self.client.get(self.url("certificate-settings")).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/certificates/").status_code, 403)

    def test_template_upload_and_reset(self):
        self.login(self.employee)
        res = self.client.post(self.url("certificate-template"), {"image": template_upload()}, format="multipart")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(res.json()["uses_default_template"])
        self.assertTrue(res.json()["template_url"].startswith("http://testserver/media/certificates/templates/"))

        preview = self.client.get(self.url("certificates/preview"), {"name": "Test Person"})
        self.assertEqual(preview["Content-Type"], "image/png")
        self.assertEqual(Image.open(io.BytesIO(preview.content)).size, (1600, 1100))

        res = self.client.delete(self.url("certificate-template"))
        self.assertTrue(res.json()["uses_default_template"])

    def test_template_validation(self):
        self.login(self.employee)
        small = self.client.post(self.url("certificate-template"), {"image": template_upload((500, 350))}, format="multipart")
        self.assertEqual(small.status_code, 400)
        fake = SimpleUploadedFile("t.png", b"nope", content_type="image/png")
        self.assertEqual(self.client.post(self.url("certificate-template"), {"image": fake}, format="multipart").status_code, 400)
        self.assertEqual(self.client.post(self.url("certificate-template"), {}, format="multipart").status_code, 400)

    def test_default_preview(self):
        self.login(self.employee)
        preview = self.client.get(self.url("certificates/preview"))
        self.assertEqual(Image.open(io.BytesIO(preview.content)).size, (1264, 848))


# ---------------------------------------------------------------------------
# Issuing
# ---------------------------------------------------------------------------

class IssueTests(CertificateTestBase):

    def test_only_attendees_get_certificates(self):
        res = self.issue()
        self.assertEqual(res.status_code, 201, res.content)
        issued = res.json()["issued"]
        self.assertEqual([c["volunteer_name"] for c in issued], ["Riya Patil"])
        certificate = Certificate.objects.get()
        self.assertRegex(certificate.certificate_id, r"^QQ-[A-Z2-9]{4}-[A-Z2-9]{4}$")
        self.assertEqual(certificate.date, datetime.date(2026, 11, 22))  # project end date
        self.assertEqual(certificate.days_attended, 2)
        self.assertEqual(certificate.issued_by, self.employee)
        with Image.open(certificate.image.path) as image:
            self.assertEqual(image.size, (1264, 848))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(certificate.certificate_id, mail.outbox[0].body)

        again = self.issue()
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["skipped"][0]["reason"], "already has a certificate")
        self.assertEqual(Certificate.objects.count(), 1)

    def test_options(self):
        res = self.issue(date="2026-12-01", volunteer_ids=[self.other.pk], notify=False)
        self.assertEqual(res.json()["issued"], [])
        self.assertIn("attendance", res.json()["skipped"][0]["reason"])
        self.assertEqual(self.issue(min_days=3).json()["issued"], [])
        res = self.issue(date="2026-12-01", notify=False)
        self.assertEqual(res.json()["issued"][0]["date"], "2026-12-01")
        self.assertEqual(len(mail.outbox), 0)

    def test_needs_certificates_turned_on(self):
        self.project.certificates_enabled = False
        self.project.save()
        res = self.issue()
        self.assertEqual(res.status_code, 400)

    def test_attendee_list(self):
        self.issue()
        data = self.client.get(f"/api/admin/projects/{self.project.pk}/certificates/").json()
        self.assertEqual(data["issued_count"], 1)
        row = data["attendees"][0]
        self.assertEqual((row["name"], row["days_attended"], row["certificate_status"]), ("Riya Patil", 2, "valid"))

    def test_snapshot_survives_renames(self):
        self.issue()
        self.volunteer.name = "Riya P. Kulkarni"
        self.volunteer.save()
        self.project.title = "Renamed"
        self.project.save()
        certificate = Certificate.objects.get()
        self.assertEqual((certificate.volunteer_name, certificate.project_title), ("Riya Patil", "Clean Water Kolhapur"))

    def test_project_with_certificates_cannot_be_hard_deleted(self):
        self.issue()
        self.login(self.admin)
        url = f"/api/admin/projects/{self.project.pk}/"
        self.client.delete(url)  # archive
        res = self.client.delete(url)
        self.assertEqual(res.status_code, 400)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())


# ---------------------------------------------------------------------------
# Admin list / revoke / download
# ---------------------------------------------------------------------------

class CertificateAdminTests(CertificateTestBase):

    def setUp(self):
        super().setUp()
        self.issue(notify=False)
        self.certificate = Certificate.objects.get()
        self.url = f"/api/admin/certificates/{self.certificate.pk}/"

    def test_list_and_search(self):
        res = self.client.get("/api/admin/certificates/", {"search": self.certificate.certificate_id}).json()
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["results"][0]["verify_url"],
                         f"https://quenchquestsocialfoundation.org/verify?id={self.certificate.certificate_id}")
        self.assertEqual(self.client.get("/api/admin/certificates/?status=revoked").json()["count"], 0)

    def test_revoke_restore_regenerate_download(self):
        res = self.client.post(f"{self.url}revoke/", {"reason": "Issued by mistake"}, format="json")
        self.assertEqual(res.json()["status"], "revoked")
        self.assertEqual(self.client.post(f"{self.url}restore/").json()["status"], "valid")
        self.assertEqual(self.client.post(f"{self.url}regenerate/").status_code, 200)
        png = self.client.get(f"{self.url}download/")
        self.assertEqual(png["Content-Type"], "image/png")
        pdf = self.client.get(f"{self.url}download/", {"type": "pdf"})
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertIn("attachment", pdf["Content-Disposition"])
        self.assertEqual(self.client.get(f"{self.url}download/", {"type": "gif"}).status_code, 400)

    def test_regenerate_project(self):
        res = self.client.post(f"/api/admin/projects/{self.project.pk}/certificates/regenerate/")
        self.assertEqual(res.json()["count"], 1)

    def test_cannot_create_directly(self):
        self.assertEqual(self.client.post("/api/admin/certificates/", {}, format="json").status_code, 405)


# ---------------------------------------------------------------------------
# Volunteer
# ---------------------------------------------------------------------------

class VolunteerCertificateTests(CertificateTestBase):

    def setUp(self):
        super().setUp()
        self.issue(notify=False)
        self.certificate = Certificate.objects.get()
        self.login(self.volunteer)

    def test_my_certificates_and_download(self):
        mine = self.client.get("/api/auth/me/certificates/").json()["results"]
        self.assertEqual(len(mine), 1)
        item = mine[0]
        self.assertEqual(item["certificate_id"], self.certificate.certificate_id)
        self.assertEqual(item["project_slug"], self.project.slug)
        self.assertTrue(item["download_url"].endswith("/download/?type=png"))

        res = self.client.get(f"/api/certificates/{self.certificate.certificate_id}/download/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "image/png")
        pdf = self.client.get(f"/api/certificates/{self.certificate.certificate_id}/download/", {"type": "pdf"})
        self.assertEqual(pdf["Content-Type"], "application/pdf")

    def test_others_cannot_download(self):
        self.login(self.other)
        self.assertEqual(self.client.get(f"/api/certificates/{self.certificate.certificate_id}/download/").status_code, 404)
        self.logout()
        self.assertEqual(self.client.get(f"/api/certificates/{self.certificate.certificate_id}/download/").status_code, 401)

    def test_revoked_cannot_be_downloaded(self):
        Certificate.objects.update(status="revoked")
        self.assertEqual(self.client.get(f"/api/certificates/{self.certificate.certificate_id}/download/").status_code, 403)
        item = self.client.get("/api/auth/me/certificates/").json()["results"][0]
        self.assertIsNone(item["download_url"])

    def test_project_and_summary_fields(self):
        project = self.client.get("/api/auth/me/projects/").json()["results"][0]
        self.assertEqual(project["certificate_id"], self.certificate.certificate_id)
        self.assertTrue(project["certificates_enabled"])
        self.assertEqual(self.client.get("/api/auth/me/summary/").json()["certificates"], 1)
        card = self.client.get(f"/api/website/projects/{self.project.slug}/").json()
        self.assertTrue(card["certificates_enabled"])


# ---------------------------------------------------------------------------
# Public verification
# ---------------------------------------------------------------------------

class VerifyTests(CertificateTestBase):

    def setUp(self):
        super().setUp()
        self.issue(notify=False)
        self.certificate = Certificate.objects.get()
        self.logout()
        cache.clear()

    def verify(self, cid):
        return self.client.get(f"/api/website/certificates/verify/{cid}/")

    def test_valid(self):
        res = self.verify(self.certificate.certificate_id)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["valid"])
        self.assertEqual((data["volunteer_name"], data["project_title"], data["date"]),
                         ("Riya Patil", "Clean Water Kolhapur", "2026-11-22"))
        self.assertEqual(data["project_slug"], self.project.slug)
        self.assertNotIn("volunteer_email", data)

    def test_id_is_forgiving(self):
        cid = self.certificate.certificate_id
        for typed in (cid.lower(), cid.replace("-", ""), f"  {cid} ", cid.replace("-", " ")):
            self.assertEqual(self.verify(typed).status_code, 200, typed)

    def test_unknown_and_revoked(self):
        res = self.verify("QQ-AAAA-AAAA")
        self.assertEqual(res.status_code, 404)
        self.assertFalse(res.json()["valid"])
        Certificate.objects.update(status="revoked")
        res = self.verify(self.certificate.certificate_id).json()
        self.assertFalse(res["valid"])
        self.assertEqual(res["status"], "revoked")

    def test_ignores_stale_tokens(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer garbage")
        self.assertEqual(self.verify(self.certificate.certificate_id).status_code, 200)

    def test_rate_limited(self):
        for _ in range(30):
            self.verify("QQ-AAAA-AAAA")
        self.assertEqual(self.verify(self.certificate.certificate_id).status_code, 429)
