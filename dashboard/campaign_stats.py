"""Raised amount, donor count and volunteer count for campaigns, computed in SQL.

Subqueries (not joins) so the sums aren't multiplied when a campaign has
both donations and volunteers.
"""
from decimal import Decimal

from django.db.models import Count, DecimalField, Exists, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from .models import CampaignVolunteer, Donation

MONEY = DecimalField(max_digits=14, decimal_places=2)


def _donation_sum(**filters):
    total = (
        Donation.objects.filter(campaign=OuterRef("pk"), **filters)
        .order_by()
        .values("campaign")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    return Coalesce(Subquery(total, output_field=MONEY), Value(Decimal("0")), output_field=MONEY)


def _count(queryset, field):
    counted = (
        queryset.filter(campaign=OuterRef("pk"))
        .order_by()
        .values("campaign")
        .annotate(n=Count(field, distinct=True))
        .values("n")[:1]
    )
    return Coalesce(Subquery(counted, output_field=IntegerField()), Value(0), output_field=IntegerField())


def with_stats(queryset, volunteer=None):
    """Annotate raised_total, donor_total, volunteer_total (+ joined, my_total for a volunteer)."""
    queryset = queryset.annotate(
        raised_total=_donation_sum(),
        donor_total=_count(Donation.objects.all(), "donor"),
        volunteer_total=_count(CampaignVolunteer.objects.all(), "volunteer"),
    )
    if volunteer is not None:
        queryset = queryset.annotate(
            joined=Exists(CampaignVolunteer.objects.filter(campaign=OuterRef("pk"), volunteer=volunteer)),
            my_total=_donation_sum(donor=volunteer),
        )
    return queryset
