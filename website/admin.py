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

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "slug", "display_order", "is_published", "show_on_home", "is_archived")
    list_filter = ("is_published", "show_on_home", "is_archived")
    search_fields = ("title", "slug")
    ordering = ("display_order",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "service", "status", "is_published", "is_featured", "is_archived")
    list_filter = ("status", "is_published", "is_featured", "is_archived", "service")
    search_fields = ("title", "slug", "location_name")
    filter_horizontal = ("volunteers",)


admin.site.register(ProjectImage)
admin.site.register(MediaAsset)
admin.site.register(FAQ)
admin.site.register(SiteSettings)
admin.site.register(ContentBlock)
admin.site.register(Page)
admin.site.register(SlugRedirect)
