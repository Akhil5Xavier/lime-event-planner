import { forwardRef, useState } from "react";

import { useDeleteEvent, useSetAttendance } from "../api/hooks";
import type { DayEvent, UserBrief } from "../api/types";
import {
  ATTENDANCE_SOURCE_LABEL,
  berlinDate,
  CATEGORY_COLOR,
  CATEGORY_LABEL,
  fmtDateTime,
  fmtNumber,
  fmtTime,
  PRIORITY_BADGE,
} from "../lib/format";

const personName = (u: UserBrief) => u.name || u.email;

interface Props {
  event: DayEvent;
  day: string;
  selected: boolean;
  onSelect: () => void;
  onEdit: () => void;
}

const EventCard = forwardRef<HTMLDivElement, Props>(function EventCard({ event, day, selected, onSelect, onEdit }, ref) {
  const rec = event.recommendation;
  const [editingAttendance, setEditingAttendance] = useState(false);
  const [attendance, setAttendance] = useState("");
  const setOverride = useSetAttendance();
  const del = useDeleteEvent();

  // Show the date too when the event started on a different day (multi-day events).
  const startsToday = berlinDate(event.start_at) === day;
  const when = startsToday ? fmtTime(event.start_at) : fmtDateTime(event.start_at);
  const until = event.end_at ? (berlinDate(event.end_at) === day ? fmtTime(event.end_at) : fmtDateTime(event.end_at)) : null;

  function saveAttendance() {
    const value = attendance.trim() === "" ? null : Number(attendance);
    if (value !== null && (!Number.isFinite(value) || value < 0)) return;
    setOverride.mutate({ id: event.id, value }, { onSuccess: () => setEditingAttendance(false) });
  }

  return (
    <div
      ref={ref}
      onClick={onSelect}
      className={`card cursor-pointer p-3 transition ${selected ? "ring-2 ring-brand" : "hover:border-gray-300"}`}
    >
      <div className="flex items-start gap-3">
        <div className="w-14 shrink-0 text-center">
          <div className="text-sm font-semibold">{when}</div>
          {until && <div className="text-xs text-gray-500">– {until}</div>}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="rounded px-1.5 py-0.5 text-[11px] font-medium text-white"
              style={{ background: CATEGORY_COLOR[event.category] }}
            >
              {CATEGORY_LABEL[event.category]}
            </span>
            <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase ${PRIORITY_BADGE[rec.priority]}`}>
              {rec.priority}
            </span>
            {event.is_manual && (
              <span className="text-[11px] text-gray-400">
                added by {event.created_by ? personName(event.created_by) : "a manager"}
              </span>
            )}
          </div>
          <h3 className="mt-1 font-semibold leading-snug">{event.title}</h3>
          <p className="text-sm text-gray-600">{event.venue?.name ?? "Venue unknown"}</p>

          <div className="mt-2 rounded-md bg-brand-light px-3 py-2 text-sm">
            <div className="font-semibold text-brand-dark">
              +{rec.extra_scooters} scooters{event.venue ? ` at ${event.venue.name}` : ""}
            </div>
            <div className="text-xs text-gray-700">
              {rec.windows.map((w) => `${w.kind === "arrival" ? "Arrivals" : "Departures"} ${fmtTime(w.start)}–${fmtTime(w.end)}`).join(" · ")}
            </div>
            <div className="mt-1 text-xs text-gray-600">
              ~{fmtNumber(rec.attendance)} visitors ({ATTENDANCE_SOURCE_LABEL[rec.attendance_source]}
              {rec.attendance_source === "manual" && event.updated_by ? ` by ${personName(event.updated_by)}` : ""})
              {event.venue?.scooter_zone_note && <div className="mt-0.5 italic">{event.venue.scooter_zone_note}</div>}
            </div>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-2" onClick={(e) => e.stopPropagation()}>
            {editingAttendance ? (
              <>
                <input
                  className="input w-32"
                  type="number"
                  min={0}
                  placeholder="visitors"
                  value={attendance}
                  onChange={(e) => setAttendance(e.target.value)}
                  autoFocus
                />
                <button className="btn-primary" onClick={saveAttendance} disabled={setOverride.isPending}>
                  Save
                </button>
                <button className="btn-secondary" onClick={() => setEditingAttendance(false)}>
                  Cancel
                </button>
                <span className="text-xs text-gray-500">Leave empty to remove your estimate.</span>
              </>
            ) : (
              <button
                className="btn-secondary"
                onClick={() => {
                  setAttendance(event.attendance_override?.toString() ?? "");
                  setEditingAttendance(true);
                }}
              >
                Adjust visitors
              </button>
            )}
            {event.is_manual && !editingAttendance && (
              <>
                <button className="btn-secondary" onClick={onEdit}>
                  Edit
                </button>
                <button
                  className="btn-danger"
                  disabled={del.isPending}
                  onClick={() => {
                    if (confirm(`Delete "${event.title}"?`)) del.mutate(event.id);
                  }}
                >
                  Delete
                </button>
              </>
            )}
            {event.url && (
              <a className="text-xs text-blue-600 hover:underline" href={event.url} target="_blank" rel="noreferrer">
                Event page ↗
              </a>
            )}
          </div>
          {event.updated_by && (event.is_manual || event.attendance_override !== null) && (
            <p className="mt-1 text-[11px] text-gray-400">
              Last changed by {personName(event.updated_by)}, {fmtDateTime(event.updated_at)}
            </p>
          )}
          {(setOverride.error || del.error) && (
            <p className="mt-1 text-xs text-red-600">{(setOverride.error ?? del.error)?.message}</p>
          )}
        </div>
      </div>
    </div>
  );
});

export default EventCard;
