"""Read-only tools the assistant's language model can call.

Each tool wraps the same service functions the REST API uses, so answers match the
calendar and day view. Results are compact JSON (free tiers have small token limits),
with Stuttgart local times. Bad input returns an "Error: ..." string as the tool result
so the model can correct itself.
"""

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.geo import normalize_name
from app.models import CATEGORIES, Event, Venue
from app.services.deployment import Recommendation, recommend
from app.services.events import effective_end
from app.services.planning import MAX_RANGE_DAYS, events_by_day, events_in_local_range, summarize_day

MAX_EVENTS = 50
MAX_VENUES = 50
MAX_TOP_DAYS = 10

_DATE = {"type": "string", "description": "Date in YYYY-MM-DD format."}
_CATEGORY = {
    "type": "string",
    "enum": list(CATEGORIES),
    "description": "Only events of this category.",
}

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": (
                "Find events in the Stuttgart area between two dates (both inclusive), with the "
                "estimated visitors and extra scooters each needs. Use for questions like "
                "'what's on next week' or 'any concerts at MHPArena in November'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": _DATE,
                    "end_date": {**_DATE, "description": "Last day to include, YYYY-MM-DD."},
                    "category": _CATEGORY,
                    "venue": {"type": "string", "description": "Part of a venue name, e.g. 'MHPArena'."},
                    "text": {"type": "string", "description": "Part of the event title, e.g. 'VfB'."},
                    "min_visitors": {"type": "integer", "description": "Only events with at least this many visitors."},
                    "limit": {"type": "integer", "description": f"Maximum events to return (default 25, max {MAX_EVENTS})."},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_day_plan",
            "description": (
                "The scooter deployment plan for one day: totals, hotspots (nearby venues grouped) "
                "with extra scooters and arrival/departure time windows, and every event that day."
            ),
            "parameters": {
                "type": "object",
                "properties": {"date": _DATE},
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_busiest_days",
            "description": "Rank days between two dates (inclusive) by extra scooters needed and visitors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": _DATE,
                    "end_date": {**_DATE, "description": "Last day to include, YYYY-MM-DD."},
                    "top": {"type": "integer", "description": f"How many days to return (default 5, max {MAX_TOP_DAYS})."},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_venues",
            "description": "Known Stuttgart venues with capacity, address and the field team's parking notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_contains": {"type": "string", "description": "Part of the venue name to filter by."},
                },
            },
        },
    },
]


class ToolInputError(ValueError):
    pass


@dataclass
class ToolContext:
    db: Session
    settings: Settings

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.settings.timezone)


# --- argument helpers ------------------------------------------------------------

def _date_arg(args: dict, name: str) -> date:
    value = args.get(name)
    if not value:
        raise ToolInputError(f"'{name}' is required (YYYY-MM-DD)")
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ToolInputError(f"'{name}' must be a date in YYYY-MM-DD format, got {value!r}")


def _int_arg(args: dict, name: str, default: int, maximum: int) -> int:
    value = args.get(name)
    if value in (None, ""):
        return default
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        raise ToolInputError(f"'{name}' must be a whole number")


def _inclusive_range(args: dict) -> tuple[date, date]:
    start, end = _date_arg(args, "start_date"), _date_arg(args, "end_date")
    if end < start:
        raise ToolInputError("end_date must be on or after start_date")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ToolInputError(f"The range is limited to {MAX_RANGE_DAYS} days; ask for a shorter period")
    return start, end


# --- formatting ----------------------------------------------------------------------

def _hm(dt, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%H:%M")


def _when(event: Event, tz: ZoneInfo) -> dict:
    start = event.start_at.astimezone(tz)
    end = effective_end(event).astimezone(tz)
    out = {"date": start.date().isoformat(), "weekday": start.strftime("%a"), "start": start.strftime("%H:%M")}
    if event.end_at is None:
        out["end"] = "unknown"
    elif end.date() == start.date():
        out["end"] = end.strftime("%H:%M")
    else:
        out["end"] = end.strftime("%Y-%m-%d %H:%M")
    return out


def _event_row(event: Event, rec: Recommendation, tz: ZoneInfo) -> dict:
    return {
        "title": event.title,
        **_when(event, tz),
        "venue": event.venue.name if event.venue else None,
        "category": event.category,
        "visitors": rec.attendance,
        "visitors_source": rec.attendance_source,
        "extra_scooters": rec.extra_scooters,
        "priority": rec.priority,
    }


def _windows(windows, tz: ZoneInfo) -> list[str]:
    return [f"{'arrivals' if w.kind == 'arrival' else 'departures'} {_hm(w.start, tz)}-{_hm(w.end, tz)}"
            for w in windows]


# --- tools -------------------------------------------------------------------------------

def search_events(ctx: ToolContext, args: dict) -> dict:
    start, end = _inclusive_range(args)
    limit = _int_arg(args, "limit", 25, MAX_EVENTS)
    category = args.get("category") or None
    venue_q = normalize_name(args.get("venue") or "")
    text_q = (args.get("text") or "").lower().strip()
    min_visitors = _int_arg(args, "min_visitors", 0, 10_000_000) if args.get("min_visitors") else 0

    rows = []
    for e in events_in_local_range(ctx.db, start, end + timedelta(days=1), category, ctx.tz):
        if venue_q:
            names = [e.venue.name, *(e.venue.aliases or "").split("|")] if e.venue else []
            if not any(venue_q in normalize_name(n) for n in names if n):
                continue
        if text_q and text_q not in e.title.lower():
            continue
        # Recommend for the first day of the event inside the asked range.
        first_day = max(start, e.start_at.astimezone(ctx.tz).date())
        rec = recommend(e, first_day, ctx.settings)
        if rec.attendance < min_visitors:
            continue
        rows.append(_event_row(e, rec, ctx.tz))
    return {"total": len(rows), "shown": min(len(rows), limit), "events": rows[:limit]}


def get_day_plan(ctx: ToolContext, args: dict) -> dict:
    day = _date_arg(args, "date")
    events = events_in_local_range(ctx.db, day, day + timedelta(days=1), None, ctx.tz)
    recs, hotspots, totals = summarize_day(events, day, ctx.settings)
    titles = {e.id: e.title for e in events}
    return {
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "totals": {
            "events": totals.event_count,
            "visitors": totals.total_attendance,
            "extra_scooters": totals.extra_scooters,
            "peak_priority": totals.priority,
        },
        "hotspots": [
            {
                "name": h.name,
                "extra_scooters": h.extra_scooters,
                "priority": h.priority,
                "events": [titles[i] for i in h.event_ids],
                "windows": _windows(h.windows, ctx.tz),
            }
            for h in hotspots
        ],
        "events": [_event_row(e, recs[e.id], ctx.tz) for e in events],
    }


def get_busiest_days(ctx: ToolContext, args: dict) -> dict:
    start, end = _inclusive_range(args)
    top = _int_arg(args, "top", 5, MAX_TOP_DAYS)
    days = []
    for d, day_events in events_by_day(ctx.db, start, end + timedelta(days=1), None, ctx.tz).items():
        recs, _, totals = summarize_day(day_events, d, ctx.settings)
        biggest = sorted(day_events, key=lambda e: recs[e.id].attendance, reverse=True)[:3]
        days.append({
            "date": d.isoformat(),
            "weekday": d.strftime("%a"),
            "events": totals.event_count,
            "visitors": totals.total_attendance,
            "extra_scooters": totals.extra_scooters,
            "priority": totals.priority,
            "biggest_events": [e.title for e in biggest],
        })
    days.sort(key=lambda x: (x["extra_scooters"], x["visitors"]), reverse=True)
    return {"days_with_events": len(days), "busiest": days[:top]}


def list_venues(ctx: ToolContext, args: dict) -> dict:
    query = normalize_name(args.get("name_contains") or "")
    venues = []
    for v in ctx.db.scalars(select(Venue).order_by(Venue.name)):
        names = [v.name, *(v.aliases or "").split("|")]
        if query and not any(query in normalize_name(n) for n in names if n):
            continue
        venues.append({"name": v.name, "address": v.address, "capacity": v.capacity,
                       "parking_note": v.scooter_zone_note})
    return {"total": len(venues), "venues": venues[:MAX_VENUES]}


TOOLS = {
    "search_events": search_events,
    "get_day_plan": get_day_plan,
    "get_busiest_days": get_busiest_days,
    "list_venues": list_venues,
}


def run_tool(name: str, raw_args: str | dict | None, ctx: ToolContext) -> str:
    """Run one tool call and return its result as text for the model. Never raises."""
    func = TOOLS.get(name)
    if func is None:
        return f"Error: unknown tool '{name}'. Available tools: {', '.join(TOOLS)}."
    try:
        if isinstance(raw_args, dict):
            args = raw_args
        else:
            args = json.loads(raw_args) if raw_args else {}
        if not isinstance(args, dict):
            raise ToolInputError("arguments must be a JSON object")
        result = func(ctx, args)
    except json.JSONDecodeError:
        return "Error: the tool arguments were not valid JSON."
    except ValueError as exc:  # ToolInputError and the services' input errors
        return f"Error: {exc}."
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
