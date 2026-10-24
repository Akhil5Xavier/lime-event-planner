import type { Category, Priority } from "../api/types";

export const TZ = "Europe/Berlin";

const timeFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const shortDateFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short" });
const dateTimeFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ,
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
// sv-SE formats as "2026-11-07 15:30:00", which is easy to turn into ISO-like wall time.
const wallFmt = new Intl.DateTimeFormat("sv-SE", {
  timeZone: TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

export const fmtTime = (iso: string) => timeFmt.format(new Date(iso));
export const fmtShortDate = (iso: string) => shortDateFmt.format(new Date(iso));
export const fmtDateTime = (iso: string) => dateTimeFmt.format(new Date(iso));
export const fmtNumber = (n: number) => n.toLocaleString("en-GB");

/** Stuttgart wall-clock time of an instant, as "YYYY-MM-DDTHH:mm:ss" (no offset). */
export function berlinWallTime(iso: string | Date): string {
  return wallFmt.format(typeof iso === "string" ? new Date(iso) : iso).replace(" ", "T");
}

/** Stuttgart calendar date of an instant, as "YYYY-MM-DD". */
export const berlinDate = (iso: string | Date) => berlinWallTime(iso).slice(0, 10);

export const todayBerlin = () => berlinDate(new Date());

/** Converts a Stuttgart wall-clock "YYYY-MM-DDTHH:mm" (e.g. from <input type=datetime-local>) to a UTC ISO string. */
export function berlinLocalToISO(local: string): string {
  const asUtc = Date.parse(`${local.length === 16 ? `${local}:00` : local}Z`);
  // Offset of Berlin at that moment; recompute once in case we crossed a DST switch.
  const offsetAt = (t: number) => Date.parse(`${berlinWallTime(new Date(t))}Z`) - t;
  let t = asUtc - offsetAt(asUtc);
  t = asUtc - offsetAt(t);
  return new Date(t).toISOString();
}

/** "YYYY-MM-DD" plus n days. */
export function addDays(date: string, n: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function fmtLongDate(date: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${date}T00:00:00Z`));
}

export const CATEGORY_LABEL: Record<Category, string> = {
  concert: "Concert",
  sport: "Sport",
  theatre: "Theatre",
  festival: "Festival",
  expo: "Trade fair",
  conference: "Conference",
  film: "Film",
  community: "Community",
  other: "Other",
};

export const CATEGORY_COLOR: Record<Category, string> = {
  concert: "#7c3aed",
  sport: "#2563eb",
  theatre: "#db2777",
  festival: "#ea580c",
  expo: "#0891b2",
  conference: "#475569",
  film: "#ca8a04",
  community: "#16a34a",
  other: "#6b7280",
};

export const PRIORITY_COLOR: Record<Priority, string> = {
  high: "#dc2626",
  medium: "#f59e0b",
  low: "#16a34a",
};

export const PRIORITY_BADGE: Record<Priority, string> = {
  high: "bg-red-100 text-red-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-green-100 text-green-800",
};

export const ATTENDANCE_SOURCE_LABEL = {
  manual: "manager estimate",
  api: "predicted by data source",
  capacity: "from venue capacity",
  default: "category default",
} as const;
