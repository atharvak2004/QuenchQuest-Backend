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
    )

    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15,default="")
    gender = models.CharField(max_length=10,choices=GENDER_CHOICES,blank=True,null=True)
    skills = models.TextField(blank=True,null=True)
    location = models.CharField(max_length=100,blank=True,null=True)
    availability = models.CharField(max_length=100,blank=True,null=True)
    password = models.CharField(max_length=255)
    otp = models.CharField(max_length=6, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
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
    )
    phone = models.CharField(max_length=15, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    choice = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="employee_role"
    )

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

    def __str__(self):
        return f"{self.username} - {self.choice}"