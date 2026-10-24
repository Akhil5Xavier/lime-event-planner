"""Ticketmaster Discovery API v2 connector.

Docs: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
The API only lets you page through the first 1000 results of a query, so the
date range is split into windows small enough to stay under that limit.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings, get_settings
from app.ingest.base import Connector, NormalizedEvent

log = logging.getLogger(__name__)

BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
PAGE_SIZE = 200
MAX_DEEP_RESULTS = 1000
WINDOW_DAYS = 14

SEGMENT_TO_CATEGORY = {
    "music": "concert",
    "sports": "sport",
    "arts & theatre": "theatre",
    "film": "film",
}
GENRE_TO_CATEGORY = {
    "festival": "festival",
    "fairs & festivals": "festival",
    "community/civic": "community",
}


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _category(raw: dict) -> str:
    classifications = raw.get("classifications") or []
    if not classifications:
        return "other"
    c = classifications[0]
    genre = ((c.get("genre") or {}).get("name") or "").lower()
    if genre in GENRE_TO_CATEGORY:
        return GENRE_TO_CATEGORY[genre]
    segment = ((c.get("segment") or {}).get("name") or "").lower()
    return SEGMENT_TO_CATEGORY.get(segment, "other")


def _best_image(raw: dict) -> str | None:
    images = raw.get("images") or []
    wide = [i for i in images if i.get("ratio") == "16_9"] or images
    if not wide:
        return None
    return max(wide, key=lambda i: i.get("width") or 0).get("url")


def normalize(raw: dict, tz_name: str = "Europe/Berlin") -> NormalizedEvent | None:
    """Map one Ticketmaster event object to a NormalizedEvent; None if it has no usable start."""
    dates = raw.get("dates") or {}
    start_info = dates.get("start") or {}
    start = _parse_dt(start_info.get("dateTime"))
    if start is None and start_info.get("localDate"):
        # Date-only events (e.g. "TBA" time): assume an evening start, local time.
        local_time = start_info.get("localTime") or "19:00:00"
        start = datetime.fromisoformat(f"{start_info['localDate']}T{local_time}").replace(
            tzinfo=ZoneInfo(tz_name)
        )
    if start is None:
        return None
    end = _parse_dt((dates.get("end") or {}).get("dateTime"))

    venues = (raw.get("_embedded") or {}).get("venues") or []
    venue = venues[0] if venues else {}
    location = venue.get("location") or {}
    lat = location.get("latitude")
    lng = location.get("longitude")

    return NormalizedEvent(
        source="ticketmaster",
        external_id=raw["id"],
        title=raw.get("name") or "Untitled event",
        start_at=start,
        end_at=end,
        category=_category(raw),
        description=raw.get("info") or raw.get("pleaseNote"),
        url=raw.get("url"),
        image_url=_best_image(raw),
        venue_name=venue.get("name"),
        venue_address=", ".join(
            p for p in [(venue.get("address") or {}).get("line1"), venue.get("postalCode"),
                        (venue.get("city") or {}).get("name")] if p
        ) or None,
        venue_lat=float(lat) if lat else None,
        venue_lng=float(lng) if lng else None,
        venue_external_ref=f"ticketmaster:{venue['id']}" if venue.get("id") else None,
    )


class TicketmasterConnector(Connector):
    name = "ticketmaster"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=30)

    def is_enabled(self) -> bool:
        return bool(self.settings.ticketmaster_api_key)

    def _windows(self, start: datetime, end: datetime):
        cur = start
        while cur < end:
            nxt = min(cur + timedelta(days=WINDOW_DAYS), end)
            yield cur, nxt
            cur = nxt

    def _get(self, params: dict) -> dict:
        for attempt in range(4):
            resp = self.client.get(BASE_URL, params=params)
            if resp.status_code == 429:
                # Rate limited (5 req/s, 5000/day on the free tier); back off.
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    def fetch(self, start: datetime, end: datetime) -> list[NormalizedEvent]:
        s = self.settings
        results: dict[str, NormalizedEvent] = {}
        for w_start, w_end in self._windows(start, end):
            page = 0
            while True:
                params = {
                    "apikey": s.ticketmaster_api_key,
                    "latlong": f"{s.city_lat},{s.city_lng}",
                    "radius": s.city_radius_km,
                    "unit": "km",
                    "countryCode": "DE",
                    "startDateTime": _fmt(w_start),
                    "endDateTime": _fmt(w_end),
                    "size": PAGE_SIZE,
                    "page": page,
                    "sort": "date,asc",
                }
                data = self._get(params)
                for raw in (data.get("_embedded") or {}).get("events") or []:
                    ev = normalize(raw, s.timezone)
                    if ev:
                        results[ev.external_id] = ev
                info = data.get("page") or {}
                page += 1
                if page >= (info.get("totalPages") or 0) or page * PAGE_SIZE >= MAX_DEEP_RESULTS:
                    if (info.get("totalElements") or 0) > MAX_DEEP_RESULTS:
                        log.warning("Ticketmaster window %s-%s truncated at %s results",
                                    w_start, w_end, MAX_DEEP_RESULTS)
                    break
                time.sleep(0.25)
        return list(results.values())
