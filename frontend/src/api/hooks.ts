import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, query } from "./client";
import type {
  CalendarDay,
  Category,
  DayData,
  EventInput,
  EventItem,
  IngestRun,
  Role,
  SourceStatus,
  User,
  Venue,
  VenueInput,
} from "./types";

const cats = (categories: Category[]) => (categories.length ? categories.join(",") : undefined);

// Every event-derived query lives under "events" so mutations can refresh them all at once.
export function useCalendarEvents(start: string | null, end: string | null, categories: Category[]) {
  return useQuery({
    queryKey: ["events", "range", start, end, categories],
    queryFn: () => api<EventItem[]>(`/api/events${query({ start, end, category: cats(categories) })}`),
    enabled: !!start && !!end,
  });
}

export function useCalendarSummary(start: string | null, end: string | null, categories: Category[]) {
  return useQuery({
    queryKey: ["events", "summary", start, end, categories],
    queryFn: () => api<CalendarDay[]>(`/api/events/summary${query({ start, end, category: cats(categories) })}`),
    enabled: !!start && !!end,
  });
}

export function useDay(date: string, categories: Category[]) {
  return useQuery({
    queryKey: ["events", "day", date, categories],
    queryFn: () => api<DayData>(`/api/events/day/${date}${query({ category: cats(categories) })}`),
  });
}

function useInvalidate(...keys: string[]) {
  const qc = useQueryClient();
  return () => Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: [k] })));
}

export function useCreateEvent() {
  const invalidate = useInvalidate("events", "venues");
  return useMutation({
    mutationFn: (body: EventInput) => api<EventItem>("/api/events", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export function useUpdateEvent() {
  const invalidate = useInvalidate("events");
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<EventInput> }) =>
      api<EventItem>(`/api/events/${id}`, { method: "PATCH", body }),
    onSuccess: invalidate,
  });
}

export function useDeleteEvent() {
  const invalidate = useInvalidate("events");
  return useMutation({
    mutationFn: (id: number) => api<void>(`/api/events/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export function useSetAttendance() {
  const invalidate = useInvalidate("events");
  return useMutation({
    mutationFn: ({ id, value }: { id: number; value: number | null }) =>
      api<EventItem>(`/api/events/${id}/attendance`, { method: "PUT", body: { attendance_override: value } }),
    onSuccess: invalidate,
  });
}

export function useVenues() {
  return useQuery({ queryKey: ["venues"], queryFn: () => api<Venue[]>("/api/venues") });
}

export function useUpdateVenue() {
  const invalidate = useInvalidate("venues", "events");
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<VenueInput> }) =>
      api<Venue>(`/api/venues/${id}`, { method: "PATCH", body }),
    onSuccess: invalidate,
  });
}

export function useSources() {
  return useQuery({ queryKey: ["ingest", "sources"], queryFn: () => api<SourceStatus[]>("/api/ingest/sources") });
}

export function useIngestRuns() {
  return useQuery({
    queryKey: ["ingest", "runs"],
    queryFn: () => api<IngestRun[]>("/api/ingest/runs"),
    // Poll while a run is in progress so the table updates on its own.
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "running") ? 3000 : false),
  });
}

export function useRunIngest() {
  const invalidate = useInvalidate("ingest", "events", "venues");
  return useMutation({
    mutationFn: () => api<{ status: string }>("/api/ingest/run", { method: "POST" }),
    // The run starts in the background; give it a moment to create its row.
    onSuccess: () => setTimeout(invalidate, 800),
  });
}

export function useUsers() {
  return useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/api/users") });
}

export function useCreateUser() {
  const invalidate = useInvalidate("users");
  return useMutation({
    mutationFn: (body: { email: string; password: string; name?: string; role: Role }) =>
      api<User>("/api/users", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export function useUpdateUser() {
  const invalidate = useInvalidate("users");
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<{ role: Role; is_active: boolean; password: string }> }) =>
      api<User>(`/api/users/${id}`, { method: "PATCH", body }),
    onSuccess: invalidate,
  });
}
