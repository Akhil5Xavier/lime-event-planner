# Chapter 4: Recommendation logic

This chapter turns stored events into answers a manager can act on: *how many extra scooters, where and when*. The code lives in `app/services/` and knows nothing about HTTP, so it can be tested directly.

---

## 4.1 `app/services/events.py`: which events run on a given day

### `DEFAULT_DURATION = timedelta(hours=3)`
Many API events have no end time. Three hours covers a typical concert or match plus some time afterwards.

### `effective_end(event)`
Returns `event.end_at`, or `start_at + 3 h` if there is no end. Every other function uses this, so the assumption lives in exactly one place.

### `day_bounds(day, tz)`
```python
start = datetime.combine(day, time.min, tzinfo=tz)
return start, datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
```
Returns the start and end of a **Stuttgart** calendar day: midnight to midnight, local time. The end is *exclusive* (`[start, end)`), so an event at exactly midnight belongs to one day only. On the days daylight saving changes, these days are 23 or 25 hours long, and this handles that automatically.

### `local_days(event, tz)`
Lists every local date an event runs on. A 3-day trade fair returns three dates.
```python
last = (effective_end(event) - timedelta(microseconds=1)).astimezone(tz).date()
```
The tiny subtraction means an event ending **exactly at midnight** doesn't count on the next day.

### `events_between(db, start, end, categories=None)`
Returns all primary (non-duplicate) events that **overlap** `[start, end)`. Two time ranges overlap when *A starts before B ends, and A ends after B starts*:
```python
Event.start_at < end,
or_(
    Event.end_at > start,
    (Event.end_at.is_(None)) & (Event.start_at > start - DEFAULT_DURATION),
),
```
The second line handles events with no end time: they count as ending 3 hours after their start.

- `Event.duplicate_of_id.is_(None)` hides duplicates.
- `joinedload(Event.venue)` (and the `created_by` and `updated_by` users) loads related rows **in the same query**. Without it, reading `event.venue` for 50 events would run 50 extra queries: the "N+1 query" problem.
- `.unique()` is needed with `joinedload` of relationships, so each event appears once.

---

## 4.2 `app/services/deployment.py`: the scooter model

The model is deliberately **simple and transparent**. A manager must be able to see why it says +62 and disagree. A black box nobody trusts gets ignored.

### Constants
```python
FILL_FACTOR = {"sport": 0.9, "concert": 0.8, "theatre": 0.75, "festival": 0.6,
               "expo": 0.5, "conference": 0.5, "film": 0.5, "community": 0.4, "other": 0.5}
DEFAULT_ATTENDANCE = {"sport": 3000, "concert": 1500, "theatre": 500, "festival": 10000,
                      "expo": 5000, "conference": 800, "film": 200, "community": 500, "other": 300}
ARRIVAL_LEAD = timedelta(minutes=90)
DEPARTURE_TAIL = timedelta(minutes=60)
MULTIDAY_OPEN, MULTIDAY_CLOSE = time(11, 0), time(23, 0)
HIGH_ATTENDANCE, MEDIUM_ATTENDANCE = 10_000, 2_000
PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2}
```
- **Fill factor:** what share of a venue's capacity usually shows up. Football matches nearly sell out; festivals spread their visitors over the day.
- **Default attendance:** used when there's no API prediction *and* no venue capacity.
- **Arrival and departure windows:** people arrive in the 90 minutes before the start, and they all leave together within an hour of the end. The departure rush is the main scooter moment.
- These are starting values. Tune them once you compare them with real Lime ride data.

### Dataclasses
- `Window(kind, start, end)`: `kind` is `"arrival"` or `"departure"`.
- `Recommendation(event_id, attendance, attendance_source, extra_scooters, priority, windows)`. Its `span` property returns `(first window start, last window end)`: the whole period this event needs scooters.
- `Hotspot(name, lat, lng, extra_scooters, priority, venue_ids, event_ids, windows)`.

### `estimate_attendance(event) -> (number, source)`
Takes the first available of:
1. `attendance_override`, source `"manual"`. The manager knows best.
2. `expected_attendance`, source `"api"`: PredictHQ's prediction.
3. Venue capacity × fill factor, source `"capacity"`.
4. The category default, source `"default"`.

**The source is returned too**, so the UI can say "~54,000 visitors (from venue capacity)". It's honest about how much to trust the number.

### `priority_for(attendance)`
`high` at 10,000+ visitors, `medium` at 2,000+, otherwise `low`.

### `recommend(event, day, settings)`
Computes the recommendation for **one event on one day**:

1. Estimate attendance.
2. **Multi-day events:** if the source is `api` or `manual`, the number is a *total* for the whole event, so divide it by the number of days. Capacity-based estimates are already per day, so they're left alone. Example: the Christmas market with 3.5 million visitors over 29 days → about 120,690 a day.
3. **Opening and closing on this day:** the real start and end on the first and last day, and 11:00–23:00 on the days in between.
4. Windows: arrival `[open − 90 min, open]` and departure `[close, close + 60 min]`.
5. Scooters: `min(ceil(daily × scooter_share), max_scooters_per_spot)`. `ceil` rounds up, because half a scooter isn't possible and too few is worse than one extra.

### `peak_concurrent(recs)`: the most needed *at the same moment*
```python
points = []
for r in recs:
    start, end = r.span
    points += [(start, r.extra_scooters), (end, -r.extra_scooters)]
points.sort(key=lambda p: (p[0], p[1]))   # at equal times, ends (negative) come first
running = peak = 0
for _, delta in points:
    running += delta
    peak = max(peak, running)
return peak
```
This is a *sweep line*. Walk through time and add an event's scooters when its span starts and remove them when it ends. The highest running total is the peak.

**Why not just add everything up?** Scooters left after an afternoon match can be ridden by evening concert-goers. **And why not "for each event, add everything that overlaps it"?** That was the first version, and it was wrong: if A overlaps B and B overlaps C, but A and C never overlap, it counts A + B + C, though no moment ever needs all three. The test in chapter 6 checks this exact case.

Sorting ends before starts at the same time means back-to-back events (one ends at 17:30, the next starts at 17:30) don't stack.

### `build_hotspots(events, recs, settings)`
Groups nearby venues into hotspots:

1. Take events that have a venue, biggest scooter need first.
2. For each, join the first existing group whose *anchor* venue is within `hotspot_radius_m` (600 m); otherwise start a new group anchored on it. Processing biggest first means the anchor, and so the hotspot's name and map position, is the most important venue.
3. For each group:
   - need = `peak_concurrent(...)`, capped at the per-spot maximum;
   - priority = the highest among its events;
   - name = the venue name, or "<venue> area" if it covers several venues;
   - windows = all of its events' windows in time order.
4. Sort by priority, then scooter count, so the Deployment plan list reads top to bottom by importance.

### Worked example: Saturday 7 Nov
| Event | Venue | Estimate | Scooters | Span |
|---|---|---|---|---|
| VfB match 15:30–17:30 | MHPArena (60,000 × 0.9) | 54,000 | ceil(270) → **150** (cap) | 14:00–18:30 |
| Pop concert 20:00–22:30 | Porsche-Arena (7,500 × 0.8) | 6,000 | 30 | 18:30–23:30 |
| Jazz 19:30, no end | Liederhalle (3,500 × 0.8) | 2,800 | 14 | 18:00–23:30 |

MHPArena and Porsche-Arena are 587 m apart, so they form one hotspot, "MHPArena area". The match ends its span at 18:30 and the concert starts at 18:30, so they're back to back: peak = max(150, 30) = **150**. Liederhalle is a separate hotspot with **14**. The day needs **+164**, with high priority because the match has 54,000 visitors.

---

## 4.3 `app/services/cleanup.py`

### `purge_old_events(db, retention_days)`
Deletes events that **ended** more than `retention_days` (365) ago, so the database doesn't grow forever.

1. Find old event IDs: `end_at < cutoff`, or no end and `start_at < cutoff`.
2. **First** delete newer duplicates that still point at an old primary. The foreign key `duplicate_of_id` would otherwise block deleting the primary.
3. Delete the old events and commit, returning how many were removed.

The nightly job runs this after each sync.

## Checkpoint

```python
from datetime import date, datetime, timedelta, timezone
from app.config import Settings
from app.models import Event, Venue
from app.services.deployment import recommend
v = Venue(id=1, name="Liederhalle", lat=48.778, lng=9.171, capacity=3500)
start = datetime(2026, 11, 7, 18, 30, tzinfo=timezone.utc)
e = Event(id=1, title="Jazz", category="concert", venue=v, start_at=start, end_at=start + timedelta(hours=2))
print(recommend(e, date(2026, 11, 7), Settings()))
```
Expected: `attendance=2800`, `extra_scooters=14`, `priority='medium'`, an arrival window from 17:00 and a departure window from 20:30 (UTC).

Next: [Chapter 5, API, CLI and migrations](05-api-cli-migrations.md).
