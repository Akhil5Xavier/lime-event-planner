import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


def send_alert(text: str) -> None:
    """Post a message to ALERT_WEBHOOK_URL (Slack-compatible {"text": ...} payload).

    Never raises: a broken webhook must not break the sync that triggered it.
    """
    url = get_settings().alert_webhook_url
    if not url:
        log.warning("Alert (no ALERT_WEBHOOK_URL set): %s", text)
        return
    try:
        httpx.post(url, json={"text": text}, timeout=10).raise_for_status()
    except httpx.HTTPError as exc:
        log.error("Could not send alert to webhook: %s", type(exc).__name__)
