from django.contrib import admin

from .models import Beneficiary, Campaign, CampaignVolunteer, Donation


class CampaignVolunteerInline(admin.TabularInline):
    model = CampaignVolunteer
    extra = 0
    raw_id_fields = ("volunteer",)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "is_published", "is_featured", "is_archived", "start_date")
    list_filter = ("status", "is_published", "is_featured", "is_archived")
    search_fields = ("title", "slug", "location_name")
    inlines = [CampaignVolunteerInline]


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ("id", "donor", "amount", "campaign", "created_at")
    list_filter = ("campaign",)
    search_fields = ("donor__name", "donor__email")
    raw_id_fields = ("donor",)


admin.site.register(Beneficiary)
