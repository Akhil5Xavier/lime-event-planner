"""PredictHQ Events API connector (optional, paid).

Docs: https://docs.predicthq.com/api/events/search-events
Its main value is `phq_attendance`, a predicted attendance per event, which
feeds the scooter recommendation better than venue capacity alone.
"""

from datetime import datetime, timezone

import httpx

from app.config import Settings, get_settings
from app.ingest.base import Connector, NormalizedEvent

BASE_URL = "https://api.predicthq.com/v1/events/"
CATEGORIES = "concerts,sports,festivals,expos,performing-arts,community,conferences"
CATEGORY_MAP = {
    "concerts": "concert",
    "sports": "sport",
    "festivals": "festival",
    "expos": "expo",
    "performing-arts": "theatre",
    "community": "community",
    "conferences": "conference",
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalize(raw: dict) -> NormalizedEvent | None:
    start = _parse_dt(raw.get("start"))
    if start is None:
        return None
    coords = ((raw.get("geo") or {}).get("geometry") or {}).get("coordinates") or raw.get("location")
    lng, lat = (coords[0], coords[1]) if coords and len(coords) == 2 else (None, None)
    venue = next((e for e in raw.get("entities") or [] if e.get("type") == "venue"), {})
    return NormalizedEvent(
        source="predicthq",
        external_id=raw["id"],
        title=raw.get("title") or "Untitled event",
        start_at=start,
        end_at=_parse_dt(raw.get("end")),
        category=CATEGORY_MAP.get(raw.get("category", ""), "other"),
        description=raw.get("description") or None,
        expected_attendance=raw.get("phq_attendance"),
        venue_name=venue.get("name"),
        venue_address=venue.get("formatted_address"),
        venue_lat=lat,
        venue_lng=lng,
        venue_external_ref=f"predicthq:{venue['entity_id']}" if venue.get("entity_id") else None,
    )


class PredictHQConnector(Connector):
    name = "predicthq"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=30)

    def is_enabled(self) -> bool:
        return bool(self.settings.predicthq_token)

    def fetch(self, start: datetime, end: datetime) -> list[NormalizedEvent]:
        s = self.settings
        headers = {"Authorization": f"Bearer {s.predicthq_token}", "Accept": "application/json"}
        params: dict | None = {
            "within": f"{s.city_radius_km}km@{s.city_lat},{s.city_lng}",
            "active.gte": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "active.lte": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "active.tz": "UTC",
            "category": CATEGORIES,
            "state": "active",
            "limit": 200,
            "sort": "start",
        }
        url: str | None = BASE_URL
        out: list[NormalizedEvent] = []
        while url:
            resp = self.client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            out.extend(ev for ev in map(normalize, data.get("results") or []) if ev)
            url = data.get("next")
            params = None  # "next" already carries the query string
        return out
