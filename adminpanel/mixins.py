from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from authentication.permissions import HasModule
from authentication.sisuser_jwt_auth import SisUserJWTAuthentication
from website.models import MediaAsset
from website.preview import PREVIEW_MAX_AGE, make_preview_token
from website.revalidate import notify_website

from .images import process_image
from .pagination import StandardPagination
from .serializers import IdsSerializer, ImageUploadSerializer, PreviewSerializer

TRUE_VALUES = {"1", "true", "yes"}
FALSE_VALUES = {"0", "false", "no"}


def bool_param(request, name):
    value = request.query_params.get(name)
    if value is None:
        return None
    value = value.lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return None


class StaffViewSet(viewsets.ModelViewSet):
    """Base for every /api/admin/ endpoint: staff token + module permission + standard pagination."""

    authentication_classes = [SisUserJWTAuthentication]
    permission_classes = [HasModule]
    pagination_class = StandardPagination
    filter_backends = [SearchFilter, OrderingFilter]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    module = "content"


class ContentViewSet(StaffViewSet):
    """Content with audit fields, soft delete and (optionally) publish state.

    Query params on list: ?archived=true|all, ?is_published=true|false, ?search=, ?ordering=
    """

    def get_queryset(self):
        qs = self.queryset.model.objects.all()
        if self.action == "list":
            archived = (self.request.query_params.get("archived") or "").lower()
            if archived in TRUE_VALUES:
                qs = qs.filter(is_archived=True)
            elif archived != "all":
                qs = qs.filter(is_archived=False)
            published = bool_param(self.request, "is_published")
            if published is not None and hasattr(qs.model, "is_published"):
                qs = qs.filter(is_published=published)
            qs = self.filter_list(qs)
        return qs

    def filter_list(self, qs):
        return qs

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if not obj.is_archived:
            obj.is_archived = True
            obj.archived_at = timezone.now()
            if hasattr(obj, "is_published"):
                obj.is_published = False
            if hasattr(obj, "is_featured"):
                obj.is_featured = False
            obj.updated_by = request.user
            obj.save()
            return Response(
                {"message": "Archived. Restore it, or delete again to remove it permanently.", "archived": True}
            )
        obj.delete()
        return Response({"message": "Deleted permanently.", "archived": False})

    @extend_schema(request=None, summary="Restore an archived item")
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        obj = self.get_object()
        obj.is_archived = False
        obj.archived_at = None
        obj.updated_by = request.user
        obj.save()
        return Response(self.get_serializer(obj).data)


class PublishMixin:
    @extend_schema(request=None, summary="Publish")
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return self._set_published(True)

    @extend_schema(request=None, summary="Unpublish (back to draft)")
    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        return self._set_published(False)

    def _set_published(self, value):
        obj = self.get_object()
        if value and obj.is_archived:
            raise ValidationError({"Error": "Restore this item before publishing it."})
        obj.is_published = value
        obj.updated_by = self.request.user
        obj.save()
        return Response(self.get_serializer(obj).data)


class ReorderMixin:
    order_field = "display_order"

    @extend_schema(request=IdsSerializer, summary='Reorder: body {"ids": [3, 1, 2]}')
    @action(detail=False, methods=["post"])
    def reorder(self, request):
        serializer = IdsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]
        model = self.queryset.model
        found = set(model.objects.filter(pk__in=ids).values_list("pk", flat=True))
        missing = [i for i in ids if i not in found]
        if missing:
            raise ValidationError({"ids": f"Unknown ids: {missing}"})
        with transaction.atomic():
            for position, pk in enumerate(ids, start=1):
                model.objects.filter(pk=pk).update(
                    **{self.order_field: position, "updated_at": timezone.now(), "updated_by": request.user}
                )
        notify_website(model._meta.model_name)
        return Response({"message": "Order saved.", "ids": ids})


class DuplicateMixin:
    def copy_object(self, obj):
        original_pk = obj.pk
        obj.pk = None
        obj.id = None
        obj._state.adding = True
        if hasattr(obj, "title"):
            obj.title = f"{obj.title} (copy)"[:200]
        if hasattr(obj, "slug"):
            obj.slug = ""
        for flag in ("is_published", "is_featured", "is_archived"):
            if hasattr(obj, flag):
                setattr(obj, flag, False)
        obj.archived_at = None
        obj.created_at = timezone.now()
        obj.updated_by = self.request.user
        obj.save()
        return original_pk, obj

    @extend_schema(request=None, summary="Duplicate as a new draft")
    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        _, copy = self.copy_object(self.get_object())
        return Response(self.get_serializer(copy).data, status=status.HTTP_201_CREATED)


class ImageMixin:
    """POST /{id}/image/ uploads (multipart `image`) or reuses a library image (`media_id`).
    DELETE /{id}/image/?field=... removes it.

    image_fields maps field name -> (web copy field or None, alt field or None).
    """

    image_fields = {}

    def _image_field(self, name):
        name = name or next(iter(self.image_fields))
        if name not in self.image_fields:
            raise ValidationError({"field": f"Use one of: {', '.join(self.image_fields)}"})
        return name

    @extend_schema(request=ImageUploadSerializer, summary="Upload or replace an image (multipart)")
    @action(detail=True, methods=["post", "delete"], parser_classes=[MultiPartParser, FormParser, JSONParser])
    def image(self, request, pk=None):
        obj = self.get_object()

        if request.method == "DELETE":
            field = self._image_field(request.query_params.get("field"))
            web_field, alt_field = self.image_fields[field]
            setattr(obj, field, "")
            if web_field:
                setattr(obj, web_field, "")
            obj.updated_by = request.user
            obj.save()
            return Response(self.get_serializer(obj).data)

        payload = ImageUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        field = self._image_field(data.get("field"))
        web_field, alt_field = self.image_fields[field]
        alt = (data.get("alt") or "").strip()

        if data.get("media_id"):
            asset = MediaAsset.objects.filter(pk=data["media_id"]).first()
            if not asset:
                raise ValidationError({"media_id": "Media item not found."})
            getattr(obj, field).name = asset.file.name
            if web_field:
                getattr(obj, web_field).name = asset.file_web.name
            alt = alt or asset.alt
        elif data.get("image"):
            processed = process_image(data["image"], field="image")
            getattr(obj, field).save(processed["original"].name, processed["original"], save=False)
            if web_field:
                getattr(obj, web_field).save(processed["web"].name, processed["web"], save=False)
        else:
            raise ValidationError({"image": "Send an image file or a media_id."})

        if alt_field:
            alt = alt or getattr(obj, alt_field)
            if not alt:
                raise ValidationError({"alt": "Alt text is required."})
            setattr(obj, alt_field, alt)

        obj.updated_by = request.user
        obj.save()
        return Response(self.get_serializer(obj).data)


class PreviewMixin:
    preview_type = None    # "service" | "project" | "page"
    public_path = None     # "/api/website/services/"

    @extend_schema(request=None, responses=PreviewSerializer, summary="Get a 1-hour preview link")
    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        obj = self.get_object()
        token = make_preview_token(self.preview_type, obj.pk)
        return Response({
            "token": token,
            "expires_in": PREVIEW_MAX_AGE,
            "api_url": request.build_absolute_uri(f"{self.public_path}{obj.slug}/?preview={token}"),
        })
