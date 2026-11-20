from django.contrib import admin

# Register your models here.
from .models import Contact

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "message",
        "created_at",
    )

    search_fields = (
        "user__name",
        "user__email",
        "message",
    )

    list_filter = (
        "created_at",
    )
    ordering = (
        "-created_at",
    )
    date_hierarchy = "created_at"

from .models import ContactNote

admin.site.register(ContactNote)
