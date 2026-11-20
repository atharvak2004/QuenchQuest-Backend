from django.db import models
from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission


class User(models.Model):
    
    ROLE_CHOICES = (
        ("employee_role", "Employee Role"),
        ("admin", "Admin"),
    )

    volunteer_id = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        editable=False
    )
    GENDER_CHOICES = (
    ("male", "Male"),
    ("female", "Female"),
    ("other", "Other"),
    ("prefer_not_to_say", "Prefer not to say"),
    )

    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15,default="")
    gender = models.CharField(max_length=20,choices=GENDER_CHOICES,blank=True,null=True)
    skills = models.TextField(blank=True,null=True)
    location = models.CharField(max_length=100,blank=True,null=True)
    availability = models.CharField(max_length=100,blank=True,null=True)
    password = models.CharField(max_length=255)
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_sent_at = models.DateTimeField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    # Deactivated volunteers can't log in; set from the admin panel.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Needed so DRF permission classes (e.g. IsAuthenticated) work when a
    # volunteer token sets request.user to this plain model.
    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def save(self, *args, **kwargs):

        if not self.volunteer_id:

            last_user = User.objects.filter(
                volunteer_id__startswith="QQ"
            ).order_by("-id").first()

            if last_user:
                last_number = int(last_user.volunteer_id[2:])
                new_number = last_number + 1
            else:
                new_number = 1

            self.volunteer_id = f"QQ{new_number:03d}"

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class SisUser(AbstractUser):

    email = models.EmailField(unique=True)
    ROLE_CHOICES = (
        ("employee_role", "Employee Role"),
        ("admin", "Admin"),
        ("editor", "Editor (content only)"),
    )

    # Admin-panel modules. Role defaults below; module_access (if set) replaces them
    # for employees and editors. Admins always get every module.
    MODULES = ("content", "inbox", "volunteers", "campaigns", "staff")
    ROLE_MODULES = {
        "admin": set(MODULES),
        "employee_role": {"content", "inbox", "volunteers", "campaigns"},
        "editor": {"content"},
    }
    MAX_FAILED_LOGINS = 5
    LOCK_MINUTES = 15
    phone = models.CharField(max_length=15, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    choice = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="employee_role"
    )
    module_access = models.JSONField(
        default=list,
        blank=True,
        help_text="Optional list of modules that replaces the role default, e.g. [\"content\", \"inbox\"]",
    )
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="sisuser_groups"
    )

    user_permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="sisuser_permissions"
    )

    @property
    def modules(self):
        if self.choice == "admin":
            return set(self.MODULES)
        if self.module_access:
            return set(self.module_access) & set(self.MODULES)
        return set(self.ROLE_MODULES.get(self.choice, set()))

    def has_module(self, module):
        return module in self.modules

    def __str__(self):
        return f"{self.username} - {self.choice}"