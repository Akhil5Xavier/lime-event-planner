import { useState, type FormEvent } from "react";
import { CircleMarker, MapContainer, TileLayer, useMapEvents } from "react-leaflet";

import { useCreateEvent, useUpdateEvent, useVenues } from "../api/hooks";
import { CATEGORIES, type Category, type EventInput, type EventItem } from "../api/types";
import { berlinLocalToISO, berlinWallTime, CATEGORY_LABEL, todayBerlin } from "../lib/format";

interface Props {
  event?: EventItem;
  defaultDate?: string;
  onClose: () => void;
  onSaved?: (event: EventItem) => void;
}

function ClickHandler({ onClick }: { onClick: (v: [number, number]) => void }) {
  useMapEvents({ click: (e) => onClick([e.latlng.lat, e.latlng.lng]) });
  return null;
}

function LocationPicker({ value, onChange }: { value: [number, number] | null; onChange: (v: [number, number]) => void }) {
  return (
    <MapContainer center={value ?? [48.7758, 9.1829]} zoom={12} className="h-48 w-full rounded-md">
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ClickHandler onClick={onChange} />
      {value && <CircleMarker center={value} radius={8} pathOptions={{ color: "#009900", fillOpacity: 0.8 }} />}
    </MapContainer>
  );
}

const toInputValue = (iso: string | null | undefined) => (iso ? berlinWallTime(iso).slice(0, 16) : "");
const optionalNumber = (s: string) => (s.trim() === "" ? null : Number(s));

export default function EventForm({ event, defaultDate, onClose, onSaved }: Props) {
  const editing = !!event;
  const venues = useVenues();
  const create = useCreateEvent();
  const update = useUpdateEvent();

  const [title, setTitle] = useState(event?.title ?? "");
  const [category, setCategory] = useState<Category>(event?.category ?? "festival");
  const [start, setStart] = useState(toInputValue(event?.start_at) || `${defaultDate ?? todayBerlin()}T18:00`);
  const [end, setEnd] = useState(toInputValue(event?.end_at));
  const [venueMode, setVenueMode] = useState<"existing" | "new">("existing");
  const [venueId, setVenueId] = useState<string>(event?.venue ? String(event.venue.id) : "");
  const [venueName, setVenueName] = useState("");
  const [venueAddress, setVenueAddress] = useState("");
  const [venueCapacity, setVenueCapacity] = useState("");
  const [location, setLocation] = useState<[number, number] | null>(null);
  const [attendance, setAttendance] = useState(event?.expected_attendance?.toString() ?? "");
  const [url, setUrl] = useState(event?.url ?? "");
  const [description, setDescription] = useState(event?.description ?? "");
  const [formError, setFormError] = useState<string | null>(null);

  const mutation = editing ? update : create;
  const error = formError ?? mutation.error?.message;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (end && end <= start) return setFormError("End must be after start.");
    if (venueMode === "new" && (!venueName.trim() || !location)) {
      return setFormError("Give the new venue a name and click its location on the map.");
    }

    const body: EventInput = {
      title: title.trim(),
      category,
      description: description.trim() || null,
      start_at: berlinLocalToISO(start),
      end_at: end ? berlinLocalToISO(end) : null,
      expected_attendance: optionalNumber(attendance),
      url: url.trim() || null,
    };
    if (venueMode === "new" && location) {
      body.new_venue = {
        name: venueName.trim(),
        address: venueAddress.trim() || null,
        lat: location[0],
        lng: location[1],
        capacity: optionalNumber(venueCapacity),
      };
    } else {
      body.venue_id = venueId ? Number(venueId) : null;
    }

    try {
      const saved = event ? await update.mutateAsync({ id: event.id, body }) : await create.mutateAsync(body);
      onSaved?.(saved);
      onClose();
    } catch {
      // shown via mutation.error
    }
  }

  return (
    <div className="fixed inset-0 z-[1000] flex items-start justify-center overflow-y-auto bg-black/40 p-4" onClick={onClose}>
      <form
        onSubmit={onSubmit}
        onClick={(e) => e.stopPropagation()}
        className="card my-8 w-full max-w-lg space-y-3 p-5"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{editing ? "Edit event" : "Add event"}</h2>
          <button type="button" className="text-gray-400 hover:text-gray-700" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        {!editing && (
          <p className="text-xs text-gray-500">
            For events the data sources miss, e.g. Volksfest, Weindorf or the Christmas market.
          </p>
        )}

        <div>
          <label className="label">Title</label>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={500} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Category</label>
            <select className="input" value={category} onChange={(e) => setCategory(e.target.value as Category)}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABEL[c]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Expected visitors</label>
            <input
              className="input"
              type="number"
              min={0}
              placeholder="from venue capacity"
              value={attendance}
              onChange={(e) => setAttendance(e.target.value)}
            />
          </div>
          <div>
            <label className="label">Start (Stuttgart time)</label>
            <input className="input" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} required />
          </div>
          <div>
            <label className="label">End (optional)</label>
            <input className="input" type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between">
            <label className="label mb-0">Venue</label>
            {!editing && (
              <div className="flex gap-1 text-xs">
                {(["existing", "new"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setVenueMode(m)}
                    className={`rounded px-2 py-0.5 ${venueMode === m ? "bg-gray-800 text-white" : "text-gray-600 hover:bg-gray-100"}`}
                  >
                    {m === "existing" ? "Known venue" : "New location"}
                  </button>
                ))}
              </div>
            )}
          </div>
          {venueMode === "existing" ? (
            <select className="input" value={venueId} onChange={(e) => setVenueId(e.target.value)}>
              <option value="">— No venue —</option>
              {(venues.data ?? []).map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                  {v.capacity ? ` (${v.capacity.toLocaleString("en-GB")})` : ""}
                </option>
              ))}
            </select>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <input className="input" placeholder="Name" value={venueName} onChange={(e) => setVenueName(e.target.value)} />
                <input
                  className="input"
                  type="number"
                  min={0}
                  placeholder="Capacity"
                  value={venueCapacity}
                  onChange={(e) => setVenueCapacity(e.target.value)}
                />
              </div>
              <input className="input" placeholder="Address" value={venueAddress} onChange={(e) => setVenueAddress(e.target.value)} />
              <LocationPicker value={location} onChange={setLocation} />
              <p className="text-xs text-gray-500">
                {location ? `Location ${location[0].toFixed(5)}, ${location[1].toFixed(5)}` : "Click the map to set the location."}
              </p>
            </div>
          )}
        </div>

        <div>
          <label className="label">Link (optional)</label>
          <input className="input" type="url" value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
        <div>
          <label className="label">Notes (optional)</label>
          <textarea className="input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>

        {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : editing ? "Save changes" : "Add event"}
          </button>
        </div>
      </form>
    </div>
  );
}
