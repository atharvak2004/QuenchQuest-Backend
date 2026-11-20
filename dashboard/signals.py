"""Refresh the website when a campaign, or anything shown on its page, changes."""
from django.db.models.signals import post_delete, post_save

from website.revalidate import notify_website

from .models import Campaign, CampaignVolunteer, Donation


def _campaign_changed(sender, instance, **kwargs):
    notify_website("campaign", instance.slug)


def _related_changed(sender, instance, **kwargs):
    # Donations and joins change raised_amount / donor_count / volunteer_count.
    campaign_id = getattr(instance, "campaign_id", None)
    if campaign_id:
        slug = Campaign.objects.filter(pk=campaign_id).values_list("slug", flat=True).first()
        if slug:
            notify_website("campaign", slug)


def connect():
    post_save.connect(_campaign_changed, sender=Campaign, dispatch_uid="revalidate-save-campaign")
    post_delete.connect(_campaign_changed, sender=Campaign, dispatch_uid="revalidate-del-campaign")
    for model in (Donation, CampaignVolunteer):
        post_save.connect(_related_changed, sender=model, dispatch_uid=f"revalidate-save-{model.__name__}")
        post_delete.connect(_related_changed, sender=model, dispatch_uid=f"revalidate-del-{model.__name__}")
