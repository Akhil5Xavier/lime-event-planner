export const CATEGORIES = [
  "concert",
  "sport",
  "theatre",
  "festival",
  "expo",
  "conference",
  "film",
  "community",
  "other",
] as const;
export type Category = (typeof CATEGORIES)[number];
export type Priority = "low" | "medium" | "high";
export type Role = "admin" | "manager";

export interface User {
  id: number;
  email: string;
  name: string | null;
  role: Role;
  is_active: boolean;
}

export interface Venue {
  id: number;
  name: string;
  address: string | null;
  lat: number;
  lng: number;
  capacity: number | null;
  aliases: string | null;
  scooter_zone_note: string | null;
}

export interface EventItem {
  id: number;
  source: string;
  title: string;
  category: Category;
  description: string | null;
  start_at: string;
  end_at: string | null;
  venue: Venue | null;
  expected_attendance: number | null;
  attendance_override: number | null;
  url: string | null;
  image_url: string | null;
  is_manual: boolean;
  created_by: UserBrief | null;
  updated_by: UserBrief | null;
  updated_at: string;
}

export interface UserBrief {
  id: number;
  email: string;
  name: string | null;
}

export interface TimeWindow {
  kind: "arrival" | "departure";
  start: string;
  end: string;
}

export interface Recommendation {
  attendance: number;
  attendance_source: "manual" | "api" | "capacity" | "default";
  extra_scooters: number;
  priority: Priority;
  windows: TimeWindow[];
}

export interface DayEvent extends EventItem {
  recommendation: Recommendation;
}

export interface Hotspot {
  name: string;
  lat: number;
  lng: number;
  extra_scooters: number;
  priority: Priority;
  venue_ids: number[];
  event_ids: number[];
  windows: TimeWindow[];
}

export interface DaySummary {
  event_count: number;
  total_attendance: number;
  extra_scooters: number;
  priority: Priority | null;
}

export interface DayData {
  date: string;
  events: DayEvent[];
  hotspots: Hotspot[];
  summary: DaySummary;
}

export interface CalendarDay extends DaySummary {
  date: string;
}

export interface IngestRun {
  id: number;
  source: string;
  trigger: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "success" | "failed";
  fetched: number;
  created: number;
  updated: number;
  duplicates: number;
  error: string | null;
}

export interface SourceStatus {
  name: string;
  enabled: boolean;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatReply {
  reply: string;
  tools_used: string[];
}

export interface ChatStatus {
  enabled: boolean;
  provider: string;
  model: string;
}

export interface VenueInput {
  name: string;
  address?: string | null;
  lat: number;
  lng: number;
  capacity?: number | null;
  scooter_zone_note?: string | null;
}

export interface EventInput {
  title: string;
  category: Category;
  description?: string | null;
  start_at: string;
  end_at?: string | null;
  venue_id?: number | null;
  new_venue?: VenueInput | null;
  expected_attendance?: number | null;
  url?: string | null;
}
