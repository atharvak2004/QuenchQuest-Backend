from django.db.models.signals import post_delete, post_save

from .models import (
    FAQ, ContentBlock, Leadership, OurImpact, Page, Project, ProjectImage, Service, SiteSettings,
)
from .revalidate import notify_website

CONTENT_MODELS = [Service, Project, Leadership, OurImpact, FAQ, SiteSettings, ContentBlock, Page]


def _content_changed(sender, instance, **kwargs):
    notify_website(sender._meta.model_name, getattr(instance, "slug", None))


def _gallery_changed(sender, instance, **kwargs):
    notify_website("project", instance.project.slug if instance.project_id else None)


def connect():
    for model in CONTENT_MODELS:
        post_save.connect(_content_changed, sender=model, dispatch_uid=f"revalidate-save-{model.__name__}")
        post_delete.connect(_content_changed, sender=model, dispatch_uid=f"revalidate-del-{model.__name__}")
    post_save.connect(_gallery_changed, sender=ProjectImage, dispatch_uid="revalidate-save-gallery")
    post_delete.connect(_gallery_changed, sender=ProjectImage, dispatch_uid="revalidate-del-gallery")
