import { useState } from "react";

import { useUpdateVenue, useVenues } from "../api/hooks";
import type { Venue } from "../api/types";

function VenueRow({ venue }: { venue: Venue }) {
  const update = useUpdateVenue();
  const [capacity, setCapacity] = useState(venue.capacity?.toString() ?? "");
  const [note, setNote] = useState(venue.scooter_zone_note ?? "");
  const dirty = capacity !== (venue.capacity?.toString() ?? "") || note !== (venue.scooter_zone_note ?? "");

  return (
    <tr className="align-top">
      <td className="px-3 py-2">
        <div className="font-medium">{venue.name}</div>
        <div className="text-xs text-gray-500">{venue.address}</div>
      </td>
      <td className="px-3 py-2">
        <input
          className="input w-28"
          type="number"
          min={0}
          placeholder="unknown"
          value={capacity}
          onChange={(e) => setCapacity(e.target.value)}
        />
      </td>
      <td className="px-3 py-2">
        <input
          className="input min-w-[16rem]"
          placeholder="e.g. Park scooters on Mercedesstraße, not the plaza"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </td>
      <td className="px-3 py-2 text-right">
        <button
          className="btn-primary"
          disabled={!dirty || update.isPending}
          onClick={() =>
            update.mutate({
              id: venue.id,
              body: { capacity: capacity.trim() === "" ? null : Number(capacity), scooter_zone_note: note.trim() || null },
            })
          }
        >
          Save
        </button>
        {update.error && <div className="mt-1 text-xs text-red-600">{update.error.message}</div>}
      </td>
    </tr>
  );
}

export default function VenuesPage() {
  const { data, isLoading, error } = useVenues();
  const [search, setSearch] = useState("");
  const shown = (data ?? []).filter((v) => v.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Venues</h1>
          <p className="text-sm text-gray-500">
            Capacity drives the visitor estimate when a data source has none. The note appears on every event card.
          </p>
        </div>
        <input className="input w-64" placeholder="Search venues" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error.message}</p>}
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-3 py-2">Venue</th>
              <th className="px-3 py-2">Capacity</th>
              <th className="px-3 py-2">Scooter zone note</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading && (
              <tr>
                <td className="px-3 py-4 text-gray-500" colSpan={4}>
                  Loading…
                </td>
              </tr>
            )}
            {shown.map((v) => (
              <VenueRow key={v.id} venue={v} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
