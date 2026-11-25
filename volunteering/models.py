import secrets

from django.db import models
from django.utils import timezone

# No 0/O or 1/I/L, so codes read out loud or off a whiteboard don't get mistyped.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def new_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class AttendanceCode(models.Model):
    """A short code staff give out at a session; entering it marks attendance at once."""

    project = models.ForeignKey("website.Project", on_delete=models.CASCADE, related_name="attendance_codes")
    code = models.CharField(max_length=12, default=new_code)
    note = models.CharField(max_length=200, blank=True, help_text='e.g. "Saturday clean-up session"')
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "authentication.SisUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("project", "code")

    @property
    def is_valid_now(self):
        now = timezone.now()
        return self.is_active and self.valid_from <= now <= self.valid_until

    def __str__(self):
        return f"{self.code} ({self.project})"


class Attendance(models.Model):
    """One volunteer, one project, one day."""

    METHOD_CHOICES = [("code", "Staff code"), ("photo", "Photo")]
    STATUS_CHOICES = [("approved", "Approved"), ("pending", "Pending"), ("rejected", "Rejected")]

    project = models.ForeignKey("website.Project", on_delete=models.CASCADE, related_name="attendance")
    volunteer = models.ForeignKey("authentication.User", on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField(default=timezone.localdate)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")

    code = models.ForeignKey(AttendanceCode, null=True, blank=True, on_delete=models.SET_NULL, related_name="uses")
    # Stored as a re-encoded WebP, which drops the original file's EXIF (incl. GPS) data.
    photo = models.ImageField(upload_to="attendance/%Y/%m/", blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    reviewed_by = models.ForeignKey(
        "authentication.SisUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=300, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        unique_together = ("project", "volunteer", "date")

    def __str__(self):
        return f"{self.volunteer} @ {self.project} on {self.date} ({self.status})"


# Certificate IDs look like QQ-7K3P-9XRM: easy to read out, impossible to guess.
CERT_GROUP = 4


def new_certificate_id():
    groups = ("".join(secrets.choice(CODE_ALPHABET) for _ in range(CERT_GROUP)) for _ in range(2))
    return "QQ-" + "-".join(groups)


class Certificate(models.Model):
    """A certificate of appreciation for a volunteer who attended a project.

    Name, project and date are copied at issue time, so later edits to the
    volunteer or project don't change a certificate that was already handed out.
    """

    STATUS_CHOICES = [("valid", "Valid"), ("revoked", "Revoked")]

    certificate_id = models.CharField(max_length=20, unique=True, default=new_certificate_id, editable=False)
    project = models.ForeignKey("website.Project", on_delete=models.PROTECT, related_name="certificates")
    volunteer = models.ForeignKey("authentication.User", on_delete=models.CASCADE, related_name="certificates")

    volunteer_name = models.CharField(max_length=100)
    project_title = models.CharField(max_length=200)
    date = models.DateField(help_text="Date printed on the certificate")
    days_attended = models.PositiveIntegerField(default=0)

    image = models.ImageField(upload_to="certificates/issued/%Y/", blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="valid")
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=300, blank=True)

    issued_by = models.ForeignKey(
        "authentication.SisUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]
        unique_together = ("project", "volunteer")

    @property
    def is_valid(self):
        return self.status == "valid"

    def __str__(self):
        return f"{self.certificate_id} - {self.volunteer_name} ({self.project_title})"
