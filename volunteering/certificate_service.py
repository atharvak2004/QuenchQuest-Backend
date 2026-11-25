"""Who gets a certificate, and issuing / re-drawing them."""
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db.models import Count, Q

from authentication.models import User

from . import certificates as drawing
from .models import Certificate, new_certificate_id


def attendees(project, min_days=1):
    """Volunteers with at least `min_days` approved attendance days on the project."""
    return (
        User.objects.annotate(
            days=Count("attendance", filter=Q(attendance__project=project, attendance__status="approved"))
        )
        .filter(days__gte=min_days)
        .order_by("name")
    )


def _unique_id():
    cid = new_certificate_id()
    while Certificate.objects.filter(certificate_id=cid).exists():
        cid = new_certificate_id()
    return cid


def draw(certificate, template, layout):
    image = drawing.render(
        template,
        name=certificate.volunteer_name,
        project=certificate.project_title,
        date=certificate.date,
        certificate_id=certificate.certificate_id,
        layout=layout,
    )
    if certificate.image:
        certificate.image.delete(save=False)
    certificate.image.save(f"{certificate.certificate_id}.png", ContentFile(drawing.to_png(image)), save=False)


def _notify(certificate):
    send_mail(
        f"Your certificate for {certificate.project_title}",
        f"Hello {certificate.volunteer_name},\n\n"
        f"Thank you for volunteering with \"{certificate.project_title}\". Your certificate of appreciation "
        "is ready: log in to your QuenchQuest dashboard to download it.\n\n"
        f"Certificate ID: {certificate.certificate_id}\n"
        f"Anyone can check it at {drawing.verify_url(certificate.certificate_id)}\n\n"
        "Team QuenchQuest",
        settings.EMAIL_HOST_USER,
        [certificate.volunteer.email],
        fail_silently=True,
    )


def issue(project, *, date, issued_by, volunteer_ids=None, min_days=1, notify=True):
    """Create certificates for attendees who don't have one yet. Returns (created, skipped)."""
    people = attendees(project, min_days)
    if volunteer_ids:
        people = people.filter(pk__in=volunteer_ids)
    already = set(Certificate.objects.filter(project=project).values_list("volunteer_id", flat=True))

    template = drawing.template_bytes(project)
    created, skipped = [], []
    for person in people:
        if person.pk in already:
            skipped.append({"volunteer": person.pk, "name": person.name, "reason": "already has a certificate"})
            continue
        if not person.is_active:
            skipped.append({"volunteer": person.pk, "name": person.name, "reason": "account is deactivated"})
            continue
        certificate = Certificate(
            certificate_id=_unique_id(),
            project=project,
            volunteer=person,
            volunteer_name=person.name,
            project_title=project.title,
            date=date,
            days_attended=person.days,
            issued_by=issued_by,
        )
        draw(certificate, template, project.certificate_layout)
        certificate.save()
        created.append(certificate)
        if notify:
            _notify(certificate)

    if volunteer_ids:
        found = {p.pk for p in people}
        for pk in volunteer_ids:
            if pk not in found:
                skipped.append({"volunteer": pk, "name": None, "reason": f"fewer than {min_days} approved attendance day(s)"})
    return created, skipped


def redraw(certificates):
    """Re-draw certificates with their project's current template and layout (same ID, name, date)."""
    templates = {}
    count = 0
    for certificate in certificates.select_related("project"):
        project = certificate.project
        if project.pk not in templates:
            templates[project.pk] = drawing.template_bytes(project)
        draw(certificate, templates[project.pk], project.certificate_layout)
        certificate.save(update_fields=["image"])
        count += 1
    return count
