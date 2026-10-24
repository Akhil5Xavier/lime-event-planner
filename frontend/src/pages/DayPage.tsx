import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useDay } from "../api/hooks";
import type { DayEvent } from "../api/types";
import CategoryFilter from "../components/CategoryFilter";
import DayMap from "../components/DayMap";
import EventCard from "../components/EventCard";
import EventForm from "../components/EventForm";
import { addDays, fmtLongDate, fmtNumber, fmtTime, PRIORITY_BADGE, todayBerlin } from "../lib/format";
import { useCategoryParam } from "../lib/useCategoryParam";

const ATTENDANCE_STEPS = [0, 500, 1000, 2000, 5000, 10000];

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="card px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className="text-xl font-semibold">{value}</div>
    </div>
  );
}

export default function DayPage() {
  const { date = todayBerlin() } = useParams();
  const navigate = useNavigate();
  const [categories, setCategories] = useCategoryParam();
  const [minAttendance, setMinAttendance] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [formFor, setFormFor] = useState<DayEvent | "new" | null>(null);
  const cardRefs = useRef(new Map<number, HTMLDivElement>());

  const { data, isLoading, error } = useDay(date, categories);

  useEffect(() => setSelectedId(null), [date]);

  const events = useMemo(
    () => (data?.events ?? []).filter((e) => e.recommendation.attendance >= minAttendance),
    [data, minAttendance],
  );
  const visibleIds = useMemo(() => new Set(events.map((e) => e.id)), [events]);
  const hotspots = useMemo(
    () => (data?.hotspots ?? []).filter((h) => h.event_ids.some((id) => visibleIds.has(id))),
    [data, visibleIds],
  );

  const selectFromMap = (id: number) => {
    setSelectedId(id);
    cardRefs.current.get(id)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const go = (d: string) => navigate({ pathname: `/day/${d}`, search: window.location.search });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to={{ pathname: "/", search: window.location.search }} className="text-sm text-gray-500 hover:underline">
            ← Calendar
          </Link>
          <h1 className="text-xl font-semibold">{fmtLongDate(date)}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-secondary" onClick={() => go(addDays(date, -1))}>
            ‹ Previous day
          </button>
          <input
            type="date"
            className="input w-40"
            value={date}
            onChange={(e) => e.target.value && go(e.target.value)}
          />
          <button className="btn-secondary" onClick={() => go(addDays(date, 1))}>
            Next day ›
          </button>
          <button className="btn-primary" onClick={() => setFormFor("new")}>
            + Add event
          </button>
        </div>
      </div>

      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error.message}</p>}

      {data && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Events" value={String(data.summary.event_count)} />
          <Stat label="Expected visitors" value={fmtNumber(data.summary.total_attendance)} />
          <Stat label="Extra scooters" value={`+${data.summary.extra_scooters}`} />
          <Stat label="Peak demand" value={data.summary.priority ?? "–"} />
        </div>
      )}

      <div className="card flex flex-wrap items-center gap-4 p-3">
        <CategoryFilter value={categories} onChange={setCategories} />
        <label className="ml-auto flex items-center gap-2 text-sm text-gray-600">
          Min. visitors
          <select className="input w-28" value={minAttendance} onChange={(e) => setMinAttendance(Number(e.target.value))}>
            {ATTENDANCE_STEPS.map((n) => (
              <option key={n} value={n}>
                {n === 0 ? "Any" : fmtNumber(n)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <section className="space-y-3">
          {isLoading && <p className="text-sm text-gray-500">Loading events…</p>}

          {hotspots.length > 0 && (
            <div className="card p-3">
              <h2 className="mb-2 text-sm font-semibold">Deployment plan</h2>
              <ul className="divide-y divide-gray-100">
                {hotspots.map((h) => (
                  <li key={`${h.lat}-${h.lng}`} className="flex flex-wrap items-center gap-2 py-1.5 text-sm">
                    <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase ${PRIORITY_BADGE[h.priority]}`}>
                      {h.priority}
                    </span>
                    <span className="font-medium">{h.name}</span>
                    <span className="font-semibold text-brand-dark">+{h.extra_scooters}</span>
                    <span className="text-xs text-gray-500">
                      from {fmtTime(h.windows[0].start)} · {h.event_ids.length} event{h.event_ids.length > 1 ? "s" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data && events.length === 0 && (
            <div className="card p-6 text-center text-sm text-gray-500">
              No events{minAttendance || categories.length ? " match the filters" : ""} on this day.
            </div>
          )}

          {events.map((e) => (
            <EventCard
              key={e.id}
              ref={(el) => {
                if (el) cardRefs.current.set(e.id, el);
                else cardRefs.current.delete(e.id);
              }}
              event={e}
              day={date}
              selected={e.id === selectedId}
              onSelect={() => setSelectedId(e.id)}
              onEdit={() => setFormFor(e)}
            />
          ))}
        </section>

        <section className="lg:sticky lg:top-4 lg:h-[calc(100vh-2rem)]">
          <div className="card h-[420px] overflow-hidden p-0 lg:h-full">
            <DayMap events={events} hotspots={hotspots} selectedEventId={selectedId} onSelectEvent={selectFromMap} />
          </div>
        </section>
      </div>

      {formFor && (
        <EventForm
          event={formFor === "new" ? undefined : formFor}
          defaultDate={date}
          onClose={() => setFormFor(null)}
        />
      )}
    </div>
  );
}
