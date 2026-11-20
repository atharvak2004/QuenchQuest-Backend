"""Tell the website to drop its cached API content after an edit."""
import json
import logging
import threading
import urllib.request

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def _send(payload):
    request = urllib.request.Request(
        settings.WEBSITE_REVALIDATE_URL,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Revalidate-Secret": settings.WEBSITE_REVALIDATE_SECRET,
        },
    )
    try:
        urllib.request.urlopen(request, timeout=5).close()
    except Exception as exc:  # never break a save because the website is down
        logger.warning("Website revalidate hook failed: %s", exc)


def notify_website(model, slug=None):
    if not settings.WEBSITE_REVALIDATE_URL:
        return
    payload = {"model": model, "slug": slug}
    transaction.on_commit(lambda: threading.Thread(target=_send, args=(payload,), daemon=True).start())
