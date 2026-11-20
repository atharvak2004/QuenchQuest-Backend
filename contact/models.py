from django.db import models
from authentication.models import SisUser, User


class Contact(models.Model):

    STATUS_CHOICES = [
        ("new", "New"),
        ("in_progress", "In progress"),
        ("replied", "Replied"),
        ("closed", "Closed"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    name = models.CharField(max_length=100, null=True, blank=True)
    contact = models.CharField(max_length=15, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)

    message = models.TextField()

    # Inbox handling (admin panel)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    assigned_to = models.ForeignKey(
        SisUser, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_contacts"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.message


class ContactNote(models.Model):
    """Internal note on an enquiry; never shown to the sender."""

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(SisUser, null=True, on_delete=models.SET_NULL, related_name="+")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
