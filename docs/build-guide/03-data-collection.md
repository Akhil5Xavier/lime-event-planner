# Chapter 3: Data collection

This chapter builds the code that fetches events from outside APIs and saves them, without duplicates, matched to the right venues.

The design has three layers:

```
connector  (ticketmaster.py, predicthq.py)   talks to one API, returns NormalizedEvent objects
store      (store.py)                        matches venues, inserts or updates rows, finds duplicates
runner     (runner.py)                       runs every connector, records each run, sends alerts
```

**Why separate them?** Connectors know nothing about the database, so you can test them with a fake HTTP response. The store knows nothing about Ticketmaster, so adding a new source means writing one new connector file and nothing else.

---

## 3.1 `app/ingest/base.py`: the common format

### `NormalizedEvent` (a dataclass)
```python
@dataclass
class NormalizedEvent:
    source: str
    external_id: str
    title: str
    start_at: datetime          # timezone-aware
    category: str = "other"
    end_at: datetime | None = None
    description: str | None = None
    url: str | None = None
    image_url: str | None = None
    expected_attendance: int | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    venue_lat: float | None = None
    venue_lng: float | None = None
    venue_external_ref: str | None = None
```
Every API returns data in its own shape. Each connector converts its data into **this one shape**, and everything after the connector only deals with `NormalizedEvent`. This is called the *adapter pattern*.

`@dataclass` generates `__init__` and friends from the field list, so there's no boilerplate.

### `Connector` (an abstract base class)
```python
class Connector(ABC):
    name: str

    @abstractmethod
    def is_enabled(self) -> bool: ...

    @abstractmethod
    def fetch(self, start: datetime, end: datetime) -> list[NormalizedEvent]: ...
```
The contract every source must follow. `ABC` with `@abstractmethod` makes Python refuse to create a connector that forgets one of these methods.

- `is_enabled()` returns false when no API key is configured. Sources without a key are skipped, not failed.
- `fetch(start, end)` returns all events in that time range.

---

## 3.2 `app/ingest/ticketmaster.py`

**Read the API docs first:** <https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/>. Before writing a connector, make one real request in your browser and save the JSON:

```
https://app.ticketmaster.com/discovery/v2/events.json?apikey=YOUR_KEY&latlong=48.7758,9.1829&radius=25&unit=km&countryCode=DE&size=5
```

The relevant shape of the response:

```json
{
  "_embedded": { "events": [ {
      "id": "...", "name": "...", "url": "...",
      "images": [ {"ratio": "16_9", "url": "...", "width": 2048} ],
      "dates": { "start": { "dateTime": "2026-11-07T14:30:00Z", "localDate": "2026-11-07", "localTime": "15:30:00" } },
      "classifications": [ { "segment": {"name": "Sports"}, "genre": {"name": "Soccer"} } ],
      "_embedded": { "venues": [ { "id": "...", "name": "MHPArena Stuttgart",
          "address": {"line1": "..."}, "postalCode": "70372", "city": {"name": "Stuttgart"},
          "location": {"latitude": "48.79227", "longitude": "9.23202"} } ] }
  } ] },
  "page": { "size": 200, "totalElements": 143, "totalPages": 1, "number": 0 }
}
```

### Constants
```python
BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
PAGE_SIZE = 200          # the API's maximum page size
MAX_DEEP_RESULTS = 1000  # the API refuses to page beyond the first 1000 results of a query
WINDOW_DAYS = 14         # split the 90 days into 14-day windows, so no single query hits 1000
```
**Why windows?** The API's "deep paging" limit means a single 90-day query for a big city could silently lose events after the first 1,000. Short windows keep each query well under the limit.

`SEGMENT_TO_CATEGORY` and `GENRE_TO_CATEGORY` map Ticketmaster's classification ("Music", "Sports", "Arts & Theatre", the genre "Festival") to our categories. The genre is checked first because it's more specific: a music *festival* should be `festival`, not `concert`.

### `_fmt(dt)`
Formats a datetime the way the API wants: `2026-11-07T14:30:00Z` (UTC, no fractional seconds).

### `_parse_dt(value)`
Parses the API's ISO strings into aware datetimes. `fromisoformat` didn't accept a trailing `Z` in older Pythons, so it's replaced with `+00:00` first.

### `_category(raw)`
Reads the first classification and maps genre, then segment, to a category, defaulting to `"other"`.

### `_best_image(raw)`
Picks the widest 16:9 image, or the widest image of any ratio if there's no 16:9 one.

### `normalize(raw, tz_name)`: one API event to a `NormalizedEvent`
The most important function in the file. Its key decisions:

1. **Start time:** use `dates.start.dateTime` (exact UTC). Some events only have `localDate` because the time is "TBA". Those get `localTime` or **19:00 Stuttgart time**, an evening start being the most common for events. This assumption is documented in the code.
2. **No usable start at all:** return `None` and skip the event, rather than crashing the whole sync.
3. **Venue:** take the first venue. Ticketmaster gives coordinates as *strings*, so they're converted with `float(...)`.
4. **`venue_external_ref = "ticketmaster:<venue id>"`:** the store remembers this, so next time the venue is matched instantly by ID.
5. **Address:** joins the parts that exist (`line1`, postal code, city), skipping missing ones.

### `TicketmasterConnector`
- `__init__(settings=None, client=None)`: both can be passed in for tests. Tests pass a fake HTTP client (`httpx.MockTransport`) so they never hit the real API. This is called *dependency injection*.
- `is_enabled()`: true if `TICKETMASTER_API_KEY` is set.
- `_windows(start, end)`: a generator that yields 14-day `(from, to)` pairs until `end`.
- `_get(params)`: makes the request with up to 4 attempts. On **HTTP 429** (rate limited; the free tier allows 5 requests per second) it waits 1, 2, 4 and 8 seconds (*exponential backoff*). `raise_for_status()` turns any other 4xx/5xx into an exception.
- `fetch(start, end)`: for each window, page through results with `latlong`, `radius`, `unit=km`, `countryCode=DE`, `size=200` and `sort=date,asc`.
  - It stops when `page >= totalPages` or at the 1,000-result limit, and logs a warning if results were cut off.
  - It waits 0.25 s between pages to stay under the rate limit.
  - Results are stored in a dict keyed by event ID, because windows overlap at their edges and the same event could be returned twice.

**Why `latlong` + `radius` instead of `city=Stuttgart`?** The city filter misses suburbs and venues registered under neighbouring towns.

---

## 3.3 `app/ingest/predicthq.py`

Optional and paid. Its value is `phq_attendance`, a *predicted* visitor count, which is better than guessing from venue capacity.

- `CATEGORY_MAP`: maps PredictHQ categories (`concerts`, `sports`, `performing-arts`, …) to ours.
- `normalize(raw)`: reads `start` and `end`, `phq_attendance`, and coordinates from `geo.geometry.coordinates` (falling back to the older `location` field). Note that GeoJSON order is **[longitude, latitude]**, the reverse of what you'd expect, and a common bug. The venue comes from the `entities` list, taking the entry with `type == "venue"`.
- `fetch(start, end)`: sends `within=25km@lat,lng`, an `active` date range, the category list and `limit=200`, with an `Authorization: Bearer <token>` header. It follows the `next` URL until there are no more pages. On the following pages `params=None`, because the `next` URL already contains the query string, and sending the params again would duplicate them.

---

## 3.4 `app/ingest/store.py`: saving events correctly

### Constants
```python
VENUE_MATCH_RADIUS_M = 150                    # "same place" for venue matching
DUPLICATE_START_TOLERANCE = timedelta(hours=1)
DUPLICATE_TITLE_SIMILARITY = 0.6              # 0 = nothing alike, 1 = identical
```

### `UpsertResult`
A small dataclass counting `created`, `updated` and `duplicates`, for the run log.

### `VenueResolver`: which venue row an event belongs to
It's created once per sync and loads **all venues into memory once**. With thousands of events, querying the database per event would be slow.

`resolve(ev)` tries, in order:

1. **External ref:** a venue already linked to this Ticketmaster venue ID. Exact and instant.
2. **Name or alias:**
   ```python
   incoming = normalize_name(ev.venue_name)
   if any(n == incoming or (len(n) >= 4 and n in incoming) for n in self._names(v)):
   ```
   An exact match, or a known name *contained in* the incoming one: `"mhparena"` is in `"mhparenastuttgart"`. The `len(n) >= 4` rule stops short aliases like "LKA" or "ICS" from matching inside unrelated names; those must match exactly.
3. **Nearest known venue within 150 m.**
4. **Otherwise create a new venue** from the API's name and coordinates (capacity unknown), and add it to the in-memory list so later events in the same sync match it.

If the event has no venue information and no coordinates, it gets no venue (`None`).

`_remember_ref(v, ev)`: when matched by name or distance, store the API's venue ID on the venue, so next time step 1 matches it.

### `_similar(a, b)`
`difflib.SequenceMatcher(...).ratio()` on normalised titles returns 0..1. It's in Python's standard library, so no extra package is needed. "VfB Stuttgart - FC Bayern München" and "VfB Stuttgart vs. FC Bayern München" score about 0.9.

### `find_duplicate(db, event)`
Looks for the **same event from a different source**: same venue, a different `source`, not itself a duplicate, starting within ±1 hour. It returns the most similar title if its score is at least 0.6.

**Why?** If both Ticketmaster and PredictHQ report the VfB match, counting it twice would recommend twice the scooters.

### `upsert_events(db, events)`
"Upsert" means *update if it exists, insert if it doesn't*. For each event:

1. Resolve the venue.
2. Look up the row by `(source, external_id)`. Create it if it's missing.
3. Copy over every field from the API. API data is the truth for imported events, so fields are simply overwritten. **`attendance_override` is never touched**, which is why the manager's estimate survives re-syncs.
4. `db.flush()` sends the changes to the database without committing, so the new row gets an `id` and the duplicate check below can see it.
5. If it's not already a duplicate, run `find_duplicate`. If one is found, set `duplicate_of_id` and **merge the best data into the primary**: copy PredictHQ's attendance, Ticketmaster's link and image, or the end time, wherever the primary is missing them.
6. Commit once at the end, so the whole batch is saved together.

---

## 3.5 `app/alerts.py`

### `send_alert(text)`
Posts `{"text": "..."}` to `ALERT_WEBHOOK_URL`. That is the format of a Slack incoming webhook, and many other tools accept it.

- With no URL configured, it just logs the alert as a warning.
- It **never raises**. A broken webhook must not break the sync that triggered the alert. It catches `httpx.HTTPError`, logs only the error type (not the URL, which may contain a token) and carries on.

---

## 3.6 `app/ingest/runner.py`: running a sync

### The two locks
```python
_lock = threading.Lock()
STALE_RUN_AFTER = timedelta(hours=2)
```
Two syncs at once would write the same rows in parallel and cause errors. Two protections:

- `_lock` stops overlaps **inside one process**: two admins clicking "Sync now" at the same moment.
- `_running_in_db(db)` stops overlaps **across processes** (several API workers plus the scheduler worker) by checking for an `IngestRun` row with `status == "running"` started in the last 2 hours. The 2-hour cutoff means a run left as "running" by a crashed process doesn't block syncing forever.

### `_scrub(message)`
Replaces the API key and token with `***` in error text. **Why:** httpx error messages include the full request URL, and Ticketmaster's key is *in* the URL (`?apikey=...`). Without this, the key would be stored in the database, shown on the Admin page and sent in alerts.

### `all_connectors()`
Returns `[TicketmasterConnector(), PredictHQConnector()]`. To add a source, add it here.

### `is_running(db)`
True if either lock says a sync is in progress. The "Sync now" endpoint uses it to answer 409 Conflict.

### `_alert_if_needed(run)`
Sends an alert when a run **failed**, or when it **succeeded but fetched 0 events**. The second case usually means an expired key or a change on the API's side, and it's silent otherwise: everything looks "successful", but the calendar slowly empties.

### `run_ingestion(trigger, connectors=None, session_factory=SessionLocal)`
1. Take the process lock, or raise `IngestAlreadyRunning`.
2. Compute the range: **yesterday** (so events already in progress get updated) to 90 days ahead.
3. Keep only enabled connectors.
4. **Create all run rows up front** as `running`, after checking the database lock. Other processes then see the sync as running for its whole duration, including the gaps between connectors.
5. For each connector, in its own session:
   - `db.merge(pending)` attaches the row created earlier to this session. `merge` returns a **new** object, and that's the one to update and return. *A real bug found by the tests: the first version returned the original objects, so callers saw "running" after the run had finished.*
   - Fetch, upsert, and record the counts and `success`.
   - On any exception: `rollback()` throws away half-written changes, the error is logged with its traceback, and the run is recorded as `failed` with the scrubbed error. **One failing source doesn't stop the others.**
   - Set `finished_at`, commit, log a one-line summary and send an alert if needed.
6. Release the lock in `finally`, so it's released even if something unexpected crashes.

`connectors` and `session_factory` are parameters so tests can pass fake connectors and a test database.

## Checkpoint

If you already have a Ticketmaster key in `backend\.env`, run this in Python from the `backend` folder:

```python
from datetime import datetime, timedelta, timezone
from app.ingest.ticketmaster import TicketmasterConnector
now = datetime.now(timezone.utc)
events = TicketmasterConnector().fetch(now, now + timedelta(days=14))
print(len(events), events[0])
```

You should see a count and one `NormalizedEvent` with a Stuttgart venue. Without a key, wait for the tests in chapter 6, which test all of this with recorded data.

Next: [Chapter 4, Recommendation logic](04-recommendation-logic.md).
