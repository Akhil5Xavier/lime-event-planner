# Chapter 9: Verification and lessons

Passing tests are necessary but not enough. This chapter covers how the whole system was verified like a real user would use it, and every bug found along the way: what went wrong, how it was noticed, and the fix. Read it as a checklist of traps to avoid.

---

## 9.1 The verification routine used

After each major part, in this order:

1. **Automated tests:** `pytest -q` (backend) and `npm run build` (frontend typecheck).
2. **Real commands:** `init-db` twice (the second run must change nothing), `create-user`, `ingest`.
3. **Real server, real HTTP:** a small Python script that logged in, created sample events through the API and printed the day view and summary, then **checked the numbers by hand** against the formula in chapter 4. Example: Friday 23 Oct = 62 (Schleyerhalle: 15,500 × 0.8 = 12,400 → 62) + 7 (Wizemann) + 6 (Staatstheater) = **+75**, matching the badge.
4. **Real browser:** log in, look at the calendar, click a day, click a card and a map marker, open the form, open the admin page, and **check the browser console for errors**.
5. **Migrations on a copy of real data:** `upgrade` → `downgrade` → `upgrade`; the event count must be unchanged.
6. **Negative checks:** the production worker started with the default secret **must refuse**; it did.

---

## 9.2 Every bug found, and what it teaches

| # | Bug | How it was found | Fix | Lesson |
|---|---|---|---|---|
| 1 | `pip install` failed: PyYAML needed a C++ compiler | Install error | Use plain `uvicorn`, not `uvicorn[standard]` | Brand-new Python versions lack prebuilt packages for a while. |
| 2 | The API key would have been saved in error messages | Code review: httpx errors include the URL, and the key is a URL parameter | `_scrub()` replaces secrets with `***`; a test checks it | Always ask "what ends up in logs and the database?" |
| 3 | Hotspot overlap overcounted (330 instead of 300) | Writing the test case A–B–C by hand | Sweep-line `peak_concurrent` | Write the tricky case as a test *before* trusting an algorithm. |
| 4 | Hotspot radius 500 m didn't group the NeckarPark venues | Calculating real distances: MHPArena–Porsche-Arena = 587 m | Default 600 m | Check settings against real geography. |
| 5 | Login rejected `@lime.test` emails | First test run: 422 | Plain `str` for the login email; real-looking test domains | Validation libraries have opinions; test with realistic data. |
| 6 | `node`/`git` "not recognized" after installing | Running them | Restart the terminal or app (PATH is read at start) | Not a code bug, but it costs time. |
| 7 | Vite's `/api` proxy couldn't reach the backend | Predicted from Node 17+ behaviour, then confirmed working after the fix | Proxy to `127.0.0.1`, not `localhost` | `localhost` can mean IPv6 `::1`. |
| 8 | Today's yellow highlight looked like "medium demand" | Looking at the calendar in the browser | Transparent today fill; green circle on the day number | Visual meaning matters as much as data. |
| 9 | The emoji in the calendar badge rendered clipped | Zoomed screenshot | Removed it | Test on real screens. |
| 10 | Map markers cut off at the edge | Browser: the red circle was outside the visible map | `ResizeObserver` → `invalidateSize()` → refit | Leaflet measures its container once; layout changes need an explicit resize. |
| 11 | `FlyTo` would re-animate on every render | Code review | Pass numbers, not a new array, to the effect | Effects depending on objects created during render re-run every render. |
| 12 | `ClickHandler` defined inside `LocationPicker` | Code review | Moved it to the top level | A component defined inside another remounts on every render. |
| 13 | The cleanup deleted duplicates twice | Re-reading the code | Removed the extra statement | Read your own diff before running it. |
| 14 | The sync returned stale "running" statuses | **Tests failed** after the multi-process lock change | Return the objects from `db.merge()` | `merge` returns a *new* object. Tests catch refactoring mistakes. |
| 15 | CI would fail: `.env` missing at `docker compose build` | Reviewing the workflow order | Create `.env` before building | `env_file` must exist even for builds. |
| 16 | The worker would always be "unhealthy" | Thinking through the inherited Dockerfile `HEALTHCHECK` | `healthcheck: disable: true` for the worker | One image used for several roles inherits every setting. |
| 17 | Backups via cron would silently fail | Knowing that cron doesn't pass the container's environment | A sleep loop instead of cron | Know your tools' environment rules. |
| 18 | nginx security headers disappearing on `/assets/` | Knowing nginx's `add_header` inheritance rule | Headers only at server level; `expires` for caching | Read the docs on inheritance and overrides. |
| 19 | The rate limit would have blocked all users together | Thinking through the proxy chain (Caddy → nginx) | `set_real_ip_from` + `X-Forwarded-For` | Behind a proxy, "the client IP" is the proxy's unless you configure it. |
| 20 | The `git commit -F -` message wasn't passed in PowerShell | The command errored | Write the message to a file, then `-F file` | PowerShell pipes and arguments differ from bash. |
| 21 | 12 of 16 real events landed on venues called "Unknown venue" | The first **real** sync; the AI assistant's answer showed "at Unknown venue" | Send `locale=*`; merge the placeholders on the next sync | The API's default locale hid German-only names. Test against the real API early; fixtures only contain what you thought of. |
| 22 | A club (Schräglage) was matched to the Marktplatz, 20,000 capacity | Looking up the venue IDs stored in the database | Match by distance only when there's no name; drop wrong links on re-sync | In a dense city centre, "within 150 m" isn't "the same place". |
| 23 | Ludwigsburg's "MHP Arena" would have matched Stuttgart's MHPArena | Searching Ticketmaster's venue list for each seed venue | Name matches must also be within 3 km | Names aren't unique; always check location as well. |
| 24 | Seed coordinates were up to 1.6 km off (Wizemann, LKA, Theaterhaus) | Comparing with Ticketmaster's coordinates | New seed values plus migration `0003`, which only moves rows still at the old values | Hand-placed coordinates need checking. A data migration must not overwrite manual corrections. |
| 26 | Calendar ‹ › buttons had no arrows in Docker only | First run in Docker; the browser console showed a CSP violation | `font-src 'self' data:`, because FullCalendar embeds its icon font as a `data:` URI | Security headers only exist in production (nginx), not on the Vite dev server: test the real stack in a browser. |
| 27 | The first backup was of an empty database | Its size: 367 bytes | The backup service waits for `backend` (migrations) to be healthy, not just `db` | "Started" doesn't mean "ready". Order services on the condition you actually need. |
| 25 | The test suite slowed to 142 s | Timing it; one bcrypt hash took 0.33 s | Hash the test password once in `conftest.py` → 32 s | Slow-by-design code (bcrypt) adds up in fixtures. |

---

## 9.3 What is still not verified

Be honest about gaps. At the end of the original build:

- **The real Ticketmaster API** was first called after the main build. It revealed bugs 21–24 above, all fixed and re-checked with a second real sync (0 unknown venues). Keep comparing synced events with ticketmaster.de now and then.
- **The Docker stack and CI** have never been run: Docker wasn't installed and the repository isn't on GitHub yet.
- **The recommendation numbers** are starting guesses. Compare `SCOOTER_SHARE`, the fill factors and the windows with real Lime ride data around past events. This is what decides whether the tool is useful.
- **Venue coordinates and capacities** are approximate; have the ops team check them.

---

## 9.4 Ideas for next steps

- Company **SSO** (Google Workspace or Okta via OpenID Connect) instead of the app's own passwords.
- **Learn from data:** store actual ride counts per hotspot and event day, and fit `SCOOTER_SHARE` per category.
- More sources: local event calendars (city of Stuttgart open data), VfB fixtures, public holidays and school holidays.
- **Weather:** rain reduces scooter use; a forecast could adjust the numbers.
- Frontend tests with Vitest and React Testing Library for the date conversion functions in `format.ts`.
- A "password reset" CLI command.

---

You've now seen every file, every function and every decision. Rebuild it chapter by chapter, run each checkpoint, and compare your files with the repository.

Back to the [guide overview](README.md).
