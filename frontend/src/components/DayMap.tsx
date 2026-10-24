import { useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";

import type { DayEvent, Hotspot } from "../api/types";
import { fmtTime, PRIORITY_COLOR } from "../lib/format";

const STUTTGART: [number, number] = [48.7758, 9.1829];

interface Props {
  events: DayEvent[];
  hotspots: Hotspot[];
  selectedEventId: number | null;
  onSelectEvent: (id: number) => void;
}

function FlyTo({ lat, lng }: { lat?: number; lng?: number }) {
  const map = useMap();
  useEffect(() => {
    if (lat !== undefined && lng !== undefined) map.flyTo([lat, lng], Math.max(map.getZoom(), 14), { duration: 0.6 });
  }, [map, lat, lng]);
  return null;
}

function FitToHotspots({ hotspots }: { hotspots: Hotspot[] }) {
  const map = useMap();
  const key = hotspots.map((h) => `${h.lat},${h.lng}`).join("|");
  useEffect(() => {
    const fit = () => {
      if (hotspots.length === 1) map.setView([hotspots[0].lat, hotspots[0].lng], 14);
      else if (hotspots.length > 1)
        map.fitBounds(hotspots.map((h) => [h.lat, h.lng] as [number, number]), { padding: [40, 40], maxZoom: 14 });
    };
    // Leaflet measures its container once; the grid/sticky layout resizes it after mount,
    // so re-measure and refit whenever the container changes size.
    const observer = new ResizeObserver(() => {
      map.invalidateSize();
      fit();
    });
    observer.observe(map.getContainer());
    fit();
    return () => observer.disconnect();
  }, [map, key]); // only refit when the set of locations changes, not on every refetch
  return null;
}

/** Hotspot circles sized by extra scooters, coloured by priority; small dots for each event venue. */
export default function DayMap({ events, hotspots, selectedEventId, onSelectEvent }: Props) {
  const selected = events.find((e) => e.id === selectedEventId);

  return (
    <MapContainer center={STUTTGART} zoom={12} scrollWheelZoom className="h-full min-h-[420px] w-full rounded-lg">
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitToHotspots hotspots={hotspots} />
      <FlyTo lat={selected?.venue?.lat} lng={selected?.venue?.lng} />

      {hotspots.map((h) => (
        <CircleMarker
          key={`hotspot-${h.lat}-${h.lng}`}
          center={[h.lat, h.lng]}
          radius={12 + Math.sqrt(h.extra_scooters) * 2.5}
          pathOptions={{ color: PRIORITY_COLOR[h.priority], fillColor: PRIORITY_COLOR[h.priority], fillOpacity: 0.25, weight: 2 }}
        >
          <Popup>
            <div className="space-y-1 text-sm">
              <div className="font-semibold">{h.name}</div>
              <div>
                <b>+{h.extra_scooters}</b> scooters · {h.priority} priority
              </div>
              <ul className="text-xs text-gray-600">
                {h.windows.map((w, i) => (
                  <li key={i}>
                    {w.kind === "arrival" ? "Arrivals" : "Departures"} {fmtTime(w.start)}–{fmtTime(w.end)}
                  </li>
                ))}
              </ul>
            </div>
          </Popup>
        </CircleMarker>
      ))}

      {events
        .filter((e) => e.venue)
        .map((e) => {
          const isSelected = e.id === selectedEventId;
          return (
            <CircleMarker
              key={`event-${e.id}`}
              center={[e.venue!.lat, e.venue!.lng]}
              radius={isSelected ? 9 : 5}
              pathOptions={{
                color: isSelected ? "#111827" : "#ffffff",
                weight: 2,
                fillColor: PRIORITY_COLOR[e.recommendation.priority],
                fillOpacity: 1,
              }}
              eventHandlers={{ click: () => onSelectEvent(e.id) }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {fmtTime(e.start_at)} {e.title} · {e.venue!.name}
              </Tooltip>
            </CircleMarker>
          );
        })}
    </MapContainer>
  );
}
