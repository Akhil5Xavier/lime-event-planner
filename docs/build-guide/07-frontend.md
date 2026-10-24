# Chapter 7: Frontend

The frontend is a **single-page app** (SPA). The browser downloads it once, and from then on it only exchanges JSON with the API. Pages switch instantly without reloading.

---

## 7.1 Project set-up

```powershell
cd D:\Projects\Lime\frontend
npm init -y
npm install react@18 react-dom@18 react-router-dom@6 @tanstack/react-query@5 `
  @fullcalendar/core@6 @fullcalendar/react@6 @fullcalendar/daygrid@6 @fullcalendar/interaction@6 `
  leaflet@1.9 react-leaflet@4 @sentry/react@10
npm install -D typescript vite@5 @vitejs/plugin-react @types/react@18 @types/react-dom@18 `
  @types/leaflet tailwindcss@3 postcss autoprefixer
```
(The backtick ` continues a command on the next line in PowerShell.)

| Package | Why |
|---|---|
| `react`, `react-dom` | The UI library. Version 18, because `react-leaflet` 4 requires it. |
| `react-router-dom` | Pages and URLs (`/day/2026-11-07`), so each day has a link you can share. |
| `@tanstack/react-query` | Fetching and caching server data, with loading and error states and refresh after changes. |
| `@fullcalendar/*` | A mature month/week calendar. Building one yourself would be a project of its own. |
| `leaflet`, `react-leaflet` | A free, open-source interactive map. |
| `@sentry/react` | Optional browser error reporting. |
| `typescript` | Types catch mistakes such as misspelled fields before you run anything. |
| `vite` + `@vitejs/plugin-react` | A very fast dev server and build tool. |
| `tailwindcss`, `postcss`, `autoprefixer` | Styling with utility classes. |

`npm install` also writes **`package-lock.json`**, which records the exact version of every package. Commit it; the Docker build uses `npm ci`, which installs exactly what's in the lock file.

### `package.json` scripts
```json
"scripts": {
  "dev": "vite",
  "build": "tsc --noEmit && vite build",
  "preview": "vite preview",
  "typecheck": "tsc --noEmit"
}
```
`build` typechecks first (`tsc --noEmit` checks types without writing files), so **a type error fails the build**.

### `tsconfig.json`
Key options: `"strict": true` (all strict checks on), `"noUnusedLocals"` and `"noUnusedParameters"` (keep the code clean), `"jsx": "react-jsx"`, `"moduleResolution": "bundler"` (how Vite resolves imports), `"noEmit": true` (Vite compiles; tsc only checks) and `"types": ["vite/client"]`, which teaches TypeScript about `import.meta.env`.

### `vite.config.ts`
```ts
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 127.0.0.1, not localhost: Node 17+ resolves localhost to ::1 but uvicorn listens on IPv4.
      "/api": "http://127.0.0.1:8000",
    },
  },
});
```
The **proxy** forwards `/api/...` from the dev server to the backend. The frontend code always calls relative `/api/...` URLs, which works the same in development (through Vite) and production (through nginx), with no CORS issues.

> **A bug found during the build:** with `"http://localhost:8000"`, Node 17+ tried IPv6 `::1` first while uvicorn only listened on IPv4 `127.0.0.1`, so every API call failed. Use `127.0.0.1`.

### `tailwind.config.js` and `postcss.config.js`
`content: ["./index.html", "./src/**/*.{ts,tsx}"]` tells Tailwind where to look for class names, so only classes you actually use end up in the CSS file. The `brand` colours (Lime green `#00C300`) are added under `theme.extend.colors`. PostCSS runs Tailwind and Autoprefixer, which adds browser prefixes.

### `index.html`
A single `<div id="root">` that React fills, and `<script type="module" src="/src/main.tsx">`.

---

## 7.2 `src/api/types.ts`: the API contract in TypeScript

TypeScript interfaces that mirror the backend schemas: `User`, `Venue`, `EventItem`, `UserBrief`, `TimeWindow`, `Recommendation`, `DayEvent`, `Hotspot`, `DaySummary`, `DayData`, `CalendarDay`, `IngestRun`, `SourceStatus`, `VenueInput` and `EventInput`.

```ts
export const CATEGORIES = ["concert", "sport", ...] as const;
export type Category = (typeof CATEGORIES)[number];
```
`as const` makes TypeScript treat the array as fixed values, so `Category` becomes the union `"concert" | "sport" | ...`. There's one list for both the dropdowns (the array) and type-checking (the type).

**Keep this file in sync with `schemas.py`.** If the backend adds a field, add it here, and the compiler then shows every place that should use it.

---

## 7.3 `src/api/client.ts`: one function for all API calls

- `BASE_URL`: `import.meta.env.VITE_API_URL ?? ""`. Empty means same origin, which is the normal case.
- `token` and `setAuthToken(value)`: the login token, held in a module variable and set by the auth context.
- `setUnauthorizedHandler(handler)`: what to do on a 401 (log out). Registered by the auth context, so this file doesn't depend on React.
- `ApiError`: an `Error` that also carries the HTTP `status`, so code can tell "not found" from "server down".
- `errorMessage(body, fallback)`: turns FastAPI's error bodies into readable text. `detail` is either a string, or a list of validation errors like `[{loc: ["body","title"], msg: "..."}]`, which becomes `"title: field required"`.
- **`api<T>(path, {method, body})`**:
  1. Sets `Accept`, sets `Content-Type: application/json` when there's a body, and adds `Authorization: Bearer <token>`.
  2. `fetch`. A 204 (no content) returns nothing.
  3. On an error status: if it's a **401 while logged in**, the token expired, so call the logout handler. Then throw an `ApiError` with a readable message.
  4. `<T>` is a generic: the caller says what type comes back, as in `api<Venue[]>("/api/venues")`.
- `query(params)`: builds `?a=1&b=2`, skipping empty values.

---

## 7.4 `src/api/hooks.ts`: React Query hooks

Each server call is wrapped in a hook. Components just write `const { data, isLoading, error } = useDay(date, categories)`.

**Query keys:** every event-related query's key starts with `"events"`: `["events", "day", date, categories]`, `["events", "summary", ...]` and so on. After any change to events, one `invalidateQueries({ queryKey: ["events"] })` refreshes the calendar, the summary and the day view together.

| Hook | Calls | Notes |
|---|---|---|
| `useCalendarEvents(start, end, categories)` | `GET /api/events` | `enabled: !!start && !!end` waits until the calendar reports its visible range. |
| `useCalendarSummary(...)` | `GET /api/events/summary` | |
| `useDay(date, categories)` | `GET /api/events/day/{date}` | |
| `useCreateEvent`, `useUpdateEvent`, `useDeleteEvent`, `useSetAttendance` | the event mutations | `onSuccess` refreshes `"events"` (and `"venues"` on create, which may add one). |
| `useVenues`, `useUpdateVenue` | venues | |
| `useSources`, `useIngestRuns`, `useRunIngest` | admin sync | `refetchInterval` polls every 3 s **only while a run is "running"**. `useRunIngest` refreshes after 800 ms, because the sync starts in the background. |
| `useUsers`, `useCreateUser`, `useUpdateUser` | admin users | |

`useInvalidate(...keys)` is a small helper returning a function that refreshes those keys.

---

## 7.5 `src/lib/format.ts`: dates and labels in Stuttgart time

**The main problem it solves:** managers' laptops might be set to another timezone (travelling, misconfigured), but the plan must always be in **Stuttgart time**.

- `TZ = "Europe/Berlin"`.
- `fmtTime`, `fmtShortDate`, `fmtDateTime` and `fmtNumber`: `Intl.DateTimeFormat` with `timeZone: TZ`, so the browser converts correctly, including daylight saving.
- **`berlinWallTime(iso)`**: an instant as Stuttgart "wall-clock" text, `"2026-11-07T15:30:00"`, without an offset. It uses the `sv-SE` (Swedish) locale because it formats as `2026-11-07 15:30:00`, almost ISO; the space is replaced with `T`. `hourCycle: "h23"` avoids "24:00".
- `berlinDate(iso)`: the first 10 characters, the Stuttgart date.
- `todayBerlin()`: today's date in Stuttgart.
- **`berlinLocalToISO(local)`**: the reverse. It converts what the user typed in a date-time input (Stuttgart time) to a real UTC instant:
  ```ts
  const asUtc = Date.parse(`${local}:00Z`);                       // pretend it's UTC
  const offsetAt = (t) => Date.parse(`${berlinWallTime(new Date(t))}Z`) - t;  // Berlin offset at t
  let t = asUtc - offsetAt(asUtc);   // first guess
  t = asUtc - offsetAt(t);           // correct once, in case the guess crossed a DST switch
  ```
  Example: "15:30" Stuttgart in November. Pretend 15:30Z; Berlin shows 16:30 then, so the offset is +1 h; 15:30Z − 1 h = 14:30Z. ✓
- `addDays(date, n)` works in UTC on date strings, so DST can't shift the day.
- `fmtLongDate(date)`: "Saturday, 7 November 2026".
- Label and colour maps: `CATEGORY_LABEL`, `CATEGORY_COLOR`, `PRIORITY_COLOR`, `PRIORITY_BADGE` (Tailwind classes) and `ATTENDANCE_SOURCE_LABEL` (for example "from venue capacity").

---

## 7.6 `src/lib/useCategoryParam.ts`

`useCategoryParam()` returns `[categories, setCategories]`, like `useState`, but stored in the **URL** (`?category=sport,concert`).

**Why the URL?** The filter survives going from calendar to day view and back, a refresh keeps it, and you can send someone a link to "sport events on Saturday". It validates values against `CATEGORIES`, so a hand-edited URL can't break anything. `{ replace: true }` stops every filter click from filling the browser's Back history.

---

## 7.7 `src/auth/AuthContext.tsx`: login state

A React **context** makes the logged-in user available to every component without passing it down by hand.

- `loadSession()` and `saveSession()` keep `{token, user}` in `localStorage` so a refresh keeps you logged in. Both are wrapped in `try/catch`, because storage can be unavailable (private browsing, blocked storage), and the app must still work.
- **`AuthProvider`**:
  - Initial state comes from storage, and `setAuthToken` is called immediately, so the very first API calls include the token.
  - `logout()` clears the token, storage, state and **the whole React Query cache**, so the next user never sees the previous user's data.
  - `useEffect(() => setUnauthorizedHandler(logout), [logout])`: an expired token anywhere means automatic logout.
  - `login(email, password)` calls the API, then stores the token and user.
  - `useMemo` and `useCallback` keep the context value stable, so components don't re-render for no reason.
- `useAuth()` returns the context, or throws if it's used outside the provider: a clear message for a programming mistake.
- **`RequireAuth({admin})`** guards routes. If not logged in, it redirects to `/login` and remembers where you were going (`state.from`). If `admin` is required and you're a manager, it redirects home.

> **Security note:** a token in `localStorage` can be read by any script running on the page, so XSS (injected scripts) is the risk to defend against. React escapes text by default, and production nginx adds a strict Content-Security-Policy that blocks injected scripts (chapter 8). The server also rejects tokens of deactivated users immediately.

---

## 7.8 `src/main.tsx` and `src/App.tsx`

### `main.tsx`
1. Imports `leaflet/dist/leaflet.css` (the map breaks visually without it) and `index.css`.
2. **Optional Sentry:** if `VITE_SENTRY_DSN` was set at build time, Sentry loads with a dynamic `import()`. When it isn't set, Vite removes this code entirely, so it costs nothing.
3. Creates the `QueryClient`:
   - `staleTime: 60_000`: data counts as fresh for 1 minute, which avoids refetching on every page switch.
   - `retry`: don't retry 4xx errors (retrying "not found" is pointless); retry server errors up to 2 times.
4. Renders the providers, outermost first: `QueryClientProvider` → `BrowserRouter` → `AuthProvider` → `App`. The order matters: `AuthProvider` uses the query client (to clear it) and the router.

### `App.tsx`
Routes:
```
/login        LoginPage           (public)
/             CalendarPage        ┐
/day/:date    DayPage             ├ inside <RequireAuth><Layout/></RequireAuth>
/venues       VenuesPage          │
/admin        AdminPage           ┘ plus <RequireAuth admin>
*             redirect to /
```
Pages are loaded with **`lazy(() => import("./pages/CalendarPage"))`**. Each page becomes its own file in the build, downloaded the first time it's opened. The login page no longer downloads FullCalendar and Leaflet; its download dropped from 192 kB to about 66 kB gzipped.

---

## 7.9 `src/index.css`

- The three Tailwind layers (`@tailwind base; components; utilities;`).
- Reusable classes in `@layer components`: `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.input`, `.label` and `.card`, built with `@apply` from Tailwind utilities. One place to change how every button looks.
- **FullCalendar tweaks:**
  - `.demand-high`, `.demand-medium` and `.demand-low` give the cell background colours.
  - `--fc-today-bg-color: transparent`, plus a green circle on today's number. *Bug found in the browser:* FullCalendar's default yellow "today" fill looked exactly like amber "medium demand", so managers would misread it.
  - A pointer cursor and green outline on hover, to show days are clickable.

---

## 7.10 Components (`src/components/`)

### `Layout.tsx`
The header (logo, Calendar, Venues, and Admin only for admins), the user's name, Sign out, and `<Outlet/>`, where the current page renders. The `Outlet` is wrapped in `<Suspense fallback="Loading…">`, which is shown while a lazy page downloads; the header stays visible. `NavLink` styles the active link automatically.

### `CategoryFilter.tsx`
A row of toggle chips, one per category with its colour dot. `toggle(c)` adds or removes the category. **An empty selection means "all"**: simpler for users than a "select all" button.

### `EventCard.tsx`
One event in the day view:
- **Time column:** just the time if it starts today; date and time for multi-day events that started earlier.
- **Badges:** category (coloured), priority, and "added by <name>" for manual events.
- **Recommendation box:** "+N scooters at <venue>", the arrival and departure windows, "~X visitors (source)", "by <name>" for manager estimates, and the venue's parking note.
- **Adjust visitors:** an inline number input. Empty removes the override; invalid numbers are ignored.
- **Edit and Delete:** only for manual events. Delete asks `confirm()` first.
- **"Last changed by <name>, <time>"** for manual or overridden events: the audit trail.
- `forwardRef` lets the day page get the card's DOM element, to scroll to it when its map marker is clicked.
- `onClick={(e) => e.stopPropagation()}` on the action row: clicking a button shouldn't also "select" the card.

### `DayMap.tsx`
- `MapContainer` centred on Stuttgart, with an OpenStreetMap `TileLayer` and its required attribution.
- **Hotspots:** a `CircleMarker` with radius `12 + √scooters × 2.5` and priority colour. The square root keeps big numbers from making huge circles. A popup shows scooters and windows.
- **Event dots:** small markers per venue. Clicking one selects that event; the selected one is bigger with a dark ring.
- `CircleMarker` rather than `Marker`, because Leaflet's default pin images break with bundlers and need extra configuration.
- **`FlyTo({lat, lng})`:** flies the map to the selected event's venue. It takes **numbers, not an array**. *A bug avoided:* an array built during rendering is a new object every render, so the effect would re-run and re-animate constantly.
- **`FitToHotspots`:** zooms the map to show all hotspots. *A bug found in the browser:* markers were cut off at the edge. Leaflet measures its container once at startup, but the page layout then resized it, so `fitBounds` used the wrong size. The fix is a `ResizeObserver` that calls `map.invalidateSize()` and refits whenever the container changes size. The effect depends on a string `key` of coordinates, so it refits only when the set of locations changes, not on every refresh.

### `EventForm.tsx`
A modal for adding and editing manual events.
- State for each field. Editing pre-fills from the event; times are shown in Stuttgart wall time (`toInputValue`).
- **Venue:** "Known venue" (a dropdown with capacities) or "New location" (name, capacity, address and a **map picker**). `LocationPicker` plus `ClickHandler` uses `useMapEvents({ click })` to set the coordinates. `ClickHandler` is defined **outside** `LocationPicker`, because a component defined inside another is a new component on every render, so it would be torn down and rebuilt each time.
- **`onSubmit`** checks the end is after the start and that a new venue has a name and location. It converts the times with `berlinLocalToISO`, builds `EventInput`, and calls create or update.
- Errors from validation or the server are shown in the form. The modal closes on success, and `onSaved` (from the calendar) navigates to the new event's day.
- Clicking the dark background closes it; `stopPropagation` on the form stops clicks inside from closing it.

---

## 7.11 Pages (`src/pages/`)

### `LoginPage.tsx`
An email and password form. On submit, it calls `login`, then navigates to where the user was going (`from`) or home. It shows the API's error message ("Invalid email or password"). `autoComplete="username"` and `"current-password"` let password managers fill it. If already logged in, it redirects away.

### `CalendarPage.tsx`
- **The timezone trick:** FullCalendar is set to `timeZone="UTC"` and fed Stuttgart wall-clock strings **without an offset** (`berlinWallTime`). It then displays exactly those times, whatever the viewer's laptop timezone. Named zones like Europe/Berlin would need an extra FullCalendar plugin.
- `datesSet` reports the visible range (the month grid spans about 6 weeks) → `range` state → both queries.
- Events are mapped to FullCalendar's format: title "Event · Venue", category colour, and `extendedProps.day` for clicks.
- `byDay` is a `Map` from date to summary, built with `useMemo`.
- `dayCellContent` draws a badge "events · +scooters" in the priority colour, with a tooltip giving details. `dayCellClassNames` adds the `demand-*` background class.
- `dateClick` and `eventClick` navigate to `/day/<date>`, **keeping the URL's search part**, so the category filter travels along.
- `firstDay={1}` starts weeks on Monday, as in Germany; `eventTimeFormat` uses 24-hour time.

### `DayPage.tsx`
- `date` comes from the URL (`useParams`), so every day has its own link.
- Previous and next day buttons and a date picker, all navigating while keeping the filter.
- **Stat tiles:** events, expected visitors, extra scooters and peak demand.
- **Min. visitors** filter, applied in the browser. `visibleIds` then hides hotspots whose events are all filtered out.
- **Deployment plan:** hotspots by priority: "+N from HH:MM · k events". The first thing a manager reads.
- Event cards on the left, the map on the right (sticky on wide screens).
- **Linked selection:** clicking a card sets `selectedId` and the map flies there. Clicking a map dot sets `selectedId` and the card is scrolled into view (`cardRefs` is a `Map` from id to DOM element, filled through the `ref` callback).
- `useEffect(() => setSelectedId(null), [date])` clears the selection when you change day.

### `VenuesPage.tsx`
A searchable table. Each `VenueRow` keeps its own editable capacity and note, and the **Save** button is enabled only when something changed (`dirty`). Why it matters: capacity drives visitor estimates, so correcting it directly improves the recommendations.

### `AdminPage.tsx`
- **`DataSources`:** source status chips ("configured" or "no API key"); a **Sync now** button, disabled with no source or during a run; and the runs table with status badges, counts and errors.
- **`Users`:** a table where role and active status can be changed inline (disabled on your own row, matching the backend rule), and an add-user form that clears after success.

## Checkpoint

Start the backend (chapter 5), then:
```powershell
cd frontend
npm run dev
```
Open <http://localhost:5173>, log in, check that the calendar shows, click a day, and click a card and a map dot. Then:
```powershell
npm run build
```
It must finish with no TypeScript errors.

Next: [Chapter 8, Deployment and CI](08-deployment-and-ci.md).
