// Types and helpers for AI visual disaster detection.

export type AlertLevel = "WATCH" | "WARNING" | "CRITICAL";
export type Risk = "LOW" | "MODERATE" | "HIGH" | "SEVERE";

export interface Analysis {
  classification: string;
  classification_label: string;
  visual_confidence: number;
  class_probabilities: Record<string, number>;
  risk_level: Risk;
  alert_level: "NONE" | AlertLevel;
  recommended_action: string;
  agent_action: string | null;
  location: { latitude: number; longitude: number };
  analysis_timestamp: string;
  weather_correlation: "confirmed" | "contradicted" | "inconclusive" | "supported_by_model" | "unavailable";
  alert_eligible: boolean;
  reasons: string[];
  model_version: string;
  evidence: {
    gauges: { rain_1h_mm: number | null; rain_24h_mm: number | null; stations: number; nearest_km: number } | null;
    model: { precipitation_mm: number | null; rain_24h_forecast_mm: number | null } | null;
    river: { station: string; km: number; level: string } | null;
    official: { level: string; source: string; station: string } | null;
    reports_nearby_6h: number;
    suggested_radius_km: number;
    corroborated: boolean;
    agent_mode: string;
    reliability: { age_hours: number | null; capture_time_source: string; location_source: string | null; gps_accuracy_m: number | null; duplicate_of: string | null };
  };
}

export interface Observation {
  image_id: string;
  image_url: string;
  capture_timestamp: string | null;
  capture_time_source: "device_clock" | "exif" | "exif_assumed_tz" | "unknown";
  upload_timestamp: string;
  latitude: number | null;
  longitude: number | null;
  gps_accuracy_meters: number | null;
  location_source: "device_gps" | "exif" | "manual" | null;
  image_source: "camera" | "upload";
  user_id: string | null;
  processing_status: "awaiting_location" | "received" | "queued" | "processing" | "done" | "failed" | "rejected";
  error: string | null;
  duplicate_of: string | null;
  incident_id: string | null;
  exif: Record<string, unknown>;
  analysis: Analysis | null;
  suggested_location?: { label: string; district: string } | null;
}

export interface Incident {
  id: string;
  disaster_type: string;
  incident_status: "PROPOSED" | "ACTIVE" | "CLOSED" | "REJECTED";
  latitude: number;
  longitude: number;
  location_label: string;
  district: string;
  province: string;
  affected_radius: number;
  suggested_radius: number;
  risk_level: Risk;
  alert_level: AlertLevel;
  suggested_level: AlertLevel;
  report_count: number;
  max_confidence: number;
  weather_correlation: string;
  proposed_message: { title: string; body: string };
  sent_message: { title: string; body: string } | null;
  verification_status: string;
  approved_by: string | null;
  exercise: boolean;
  first_detected_at: string;
  last_updated_at: string;
  approved_at: string | null;
  closed_at: string | null;
  close_note: string | null;
  escalation_suggested: boolean;
  notified?: number;
  users_in_radius?: number;
  observations?: Observation[];
  users_by_radius?: Record<string, number>;
  delivery_summary?: { notification_channel: string; notification_status: string; level: string; n: number }[];
  history?: { at: string; actor: string; action: string; payload: Record<string, unknown> }[];
  channels_configured?: Record<string, boolean>;
  external_sending_enabled?: boolean;
}

export interface Areas {
  provinces: string[];
  districts: { name: string; province: string; hq: string; lat: number; lon: number }[];
  cities: { name: string; district: string; lat: number; lon: number; radius_km: number }[];
}

export const RADII = [1, 3, 5, 10] as const;
export const NEPAL_CENTER: [number, number] = [84.1, 28.3];
export const MAP_STYLE = "https://tiles.openfreemap.org/styles/positron";

export const ALERT_COLOR: Record<string, string> = {
  NONE: "#6c7a89", INFO: "#5b8def", MONITOR: "#5b8def", WATCH: "#edc948", WARNING: "#e8a33d", CRITICAL: "#d1495b",
};
export const RISK_COLOR: Record<Risk, string> = { LOW: "#4f9d69", MODERATE: "#edc948", HIGH: "#e8a33d", SEVERE: "#d1495b" };

export const ACTION_TEXT: Record<string, string> = {
  NO_ALERT: "No alert", MONITOR: "Keep monitoring", ISSUE_WATCH: "Propose a WATCH", ISSUE_WARNING: "Propose a WARNING",
  ISSUE_CRITICAL_ALERT: "Propose a CRITICAL alert", REQUEST_ADDITIONAL_EVIDENCE: "Ask for more evidence",
};
export const CORRELATION_TEXT: Record<string, string> = {
  confirmed: "Confirmed by rain gauges near the photo",
  contradicted: "Rain gauges near the photo recorded little rain",
  inconclusive: "Rain gauges show some rain, not enough to confirm",
  supported_by_model: "Weather model shows heavy rain (modelled, not measured)",
  unavailable: "No weather data for this place and time (not treated as confirmation)",
};
export const TIME_SOURCE_TEXT: Record<string, string> = {
  device_clock: "camera (device clock)", exif: "photo metadata (EXIF)", exif_assumed_tz: "photo metadata, your timezone assumed",
  unknown: "unknown — only the upload time is known",
};
export const LOCATION_SOURCE_TEXT: Record<string, string> = {
  device_gps: "device GPS", exif: "photo metadata (EXIF GPS)", manual: "chosen on the map",
};

/** ISO-8601 with the device's local UTC offset, e.g. 2026-07-14T16:05:09.120+05:45 */
export function isoLocal(d: Date = new Date()): string {
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const pad = (n: number, w = 2) => String(Math.floor(Math.abs(n))).padStart(w, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}${sign}${pad(off / 60)}:${pad(off % 60)}`;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function circle(lon: number, lat: number, km: number, n = 64): [number, number][] {
  const pts: [number, number][] = [];
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * 2 * Math.PI;
    const dLat = (km / 111.32) * Math.sin(a);
    const dLon = (km / (111.32 * Math.cos((lat * Math.PI) / 180))) * Math.cos(a);
    pts.push([lon + dLon, lat + dLat]);
  }
  return pts;
}

export const MAX_UPLOAD_MB = 10;
export const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];

export function checkFile(f: File): string | null {
  if (!ACCEPTED.includes(f.type)) return "Please choose a JPEG, PNG or WebP photo.";
  if (f.size > MAX_UPLOAD_MB * 1024 * 1024) return `The photo is larger than ${MAX_UPLOAD_MB} MB.`;
  return null;
}

export function getPosition(timeoutMs = 15000): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) { reject(new Error("This device has no GPS / location service.")); return; }
    navigator.geolocation.getCurrentPosition(resolve, (e) => reject(new Error(e.message || "Location permission was denied.")),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 0 });
  });
}
