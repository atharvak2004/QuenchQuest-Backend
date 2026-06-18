from django.contrib import admin

# Register your models here.
from .models import *


@admin.register(OurImpact)
class OurImpactAdmin(admin.ModelAdmin):

    list_display = (
        "children_women_supported",
        "skill_awareness_programs",
        "communities_reached",
        "date",
    )

    list_filter = (
        "date",
    )

    ordering = (
        "-date",
    )

    date_hierarchy = "date"

@admin.register(Leadership)
class LeadershipAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "name",
        "position",
    )

    search_fields = (
        "name",
        "position",
    )

    ordering = (
        "name",
    )


@admin.register(ProgramCard)
class ProgramCardAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "title",
    )

    search_fields = (
        "title",
    )

    ordering = (
        "title",
    )