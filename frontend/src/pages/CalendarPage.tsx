import type { DatesSetArg, DayCellContentArg, EventClickArg, EventInput } from "@fullcalendar/core";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin, { type DateClickArg } from "@fullcalendar/interaction";
import FullCalendar from "@fullcalendar/react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCalendarEvents, useCalendarSummary } from "../api/hooks";
import type { CalendarDay } from "../api/types";
import CategoryFilter from "../components/CategoryFilter";
import EventForm from "../components/EventForm";
import { berlinDate, berlinWallTime, CATEGORY_COLOR, fmtNumber, PRIORITY_COLOR } from "../lib/format";
import { useCategoryParam } from "../lib/useCategoryParam";

// The calendar runs in "UTC" mode and is fed Stuttgart wall-clock times without an
// offset, so it always shows Stuttgart time regardless of the viewer's own timezone.
const isoDate = (d: Date) => d.toISOString().slice(0, 10);

export default function CalendarPage() {
  const navigate = useNavigate();
  const [categories, setCategories] = useCategoryParam();
  const [range, setRange] = useState<{ start: string; end: string } | null>(null);
  const [showForm, setShowForm] = useState(false);

  const events = useCalendarEvents(range?.start ?? null, range?.end ?? null, categories);
  const summary = useCalendarSummary(range?.start ?? null, range?.end ?? null, categories);

  const byDay = useMemo(() => {
    const m = new Map<string, CalendarDay>();
    for (const d of summary.data ?? []) m.set(d.date, d);
    return m;
  }, [summary.data]);

  const calendarEvents: EventInput[] = useMemo(
    () =>
      (events.data ?? []).map((e) => ({
        id: String(e.id),
        title: e.venue ? `${e.title} · ${e.venue.name}` : e.title,
        start: berlinWallTime(e.start_at),
        end: e.end_at ? berlinWallTime(e.end_at) : undefined,
        color: CATEGORY_COLOR[e.category],
        extendedProps: { day: berlinDate(e.start_at) },
      })),
    [events.data],
  );

  const goToDay = (date: string) => navigate({ pathname: `/day/${date}`, search: window.location.search });

  const renderDayCell = (arg: DayCellContentArg) => {
    const info = byDay.get(isoDate(arg.date));
    return (
      <div className="flex w-full items-center justify-between gap-1 px-1">
        {info ? (
          <span
            className="rounded px-1 text-[11px] font-semibold text-white"
            style={{ background: info.priority ? PRIORITY_COLOR[info.priority] : "#6b7280" }}
            title={`${info.event_count} events · ~${fmtNumber(info.total_attendance)} visitors · +${info.extra_scooters} scooters`}
          >
            {info.event_count} · +{info.extra_scooters}
          </span>
        ) : (
          <span />
        )}
        <span>{arg.dayNumberText}</span>
      </div>
    );
  };

  const error = events.error ?? summary.error;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Events in Stuttgart</h1>
          <p className="text-sm text-gray-500">
            Click a day to see its events, the map and where to put extra scooters.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowForm(true)}>
          + Add event
        </button>
      </div>

      <div className="card flex flex-wrap items-center justify-between gap-3 p-3">
        <CategoryFilter value={categories} onChange={setCategories} />
        <div className="flex items-center gap-3 text-xs text-gray-600">
          <span>Demand:</span>
          {(["high", "medium", "low"] as const).map((p) => (
            <span key={p} className="flex items-center gap-1">
              <span className="h-3 w-3 rounded" style={{ background: PRIORITY_COLOR[p] }} />
              {p}
            </span>
          ))}
          <span className="text-gray-400">badge = events · extra scooters</span>
        </div>
      </div>

      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error.message}</p>}

      <div className="card p-3">
        <FullCalendar
          plugins={[dayGridPlugin, interactionPlugin]}
          initialView="dayGridMonth"
          timeZone="UTC"
          firstDay={1}
          height="auto"
          headerToolbar={{ left: "prev,next today", center: "title", right: "dayGridMonth,dayGridWeek" }}
          buttonText={{ today: "Today", month: "Month", week: "Week" }}
          eventTimeFormat={{ hour: "2-digit", minute: "2-digit", hour12: false }}
          dayMaxEvents={3}
          events={calendarEvents}
          dayCellContent={renderDayCell}
          dayCellClassNames={(arg) => {
            const p = byDay.get(isoDate(arg.date))?.priority;
            return p ? [`demand-${p}`] : [];
          }}
          datesSet={(arg: DatesSetArg) => setRange({ start: isoDate(arg.start), end: isoDate(arg.end) })}
          dateClick={(arg: DateClickArg) => goToDay(isoDate(arg.date))}
          eventClick={(arg: EventClickArg) => {
            arg.jsEvent.preventDefault();
            goToDay(arg.event.extendedProps.day as string);
          }}
        />
        {(events.isFetching || summary.isFetching) && <p className="mt-2 text-xs text-gray-400">Loading…</p>}
      </div>

      {showForm && <EventForm onClose={() => setShowForm(false)} onSaved={(e) => goToDay(berlinDate(e.start_at))} />}
    </div>
  );
}
