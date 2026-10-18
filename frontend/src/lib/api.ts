export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetcher<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return res.json() as Promise<T>;
}

export type RiskLevel = "NORMAL" | "WATCH" | "WARNING" | "CRITICAL" | "UNKNOWN";

export interface PointFeature<P> {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: P;
}
export interface FC<P> {
  type: "FeatureCollection";
  features: PointFeature<P>[];
  observed_at?: string | null;
}

export interface GridProps {
  temperature_c: number | null;
  humidity_pct: number | null;
  precipitation_mm: number | null;
  rain_24h_forecast_mm: number | null;
  wind_speed_kmh: number | null;
  wind_dir_deg: number | null;
  wind_gust_kmh: number | null;
  cloud_cover_pct: number | null;
  weather_code: number | null;
  apparent_temp_c: number | null;
  pressure_hpa: number | null;
  tmax_3d_c: number | null;
  observed_at: string;
}

export interface StationProps {
  id: number;
  source: string;
  name: string;
  basin: string | null;
  district: string | null;
  value: number | null;
  observed_at: string | null;
  quality: string | null;
  rain_24h_mm: number | null;
  watch_level: number | null;
  warning_level: number | null;
  danger_level: number | null;
  ratio_to_warning: number | null;
  trend: string | null;
  risk_level: RiskLevel;
  confidence: string | null;
  reasons: string[];
}

export interface WeatherSummary {
  n: number;
  t_avg: number | null;
  t_min: number | null;
  t_max: number | null;
  wind_max: number | null;
  gust_max: number | null;
  precip_max: number | null;
  rain24_max: number | null;
  rh_avg: number | null;
  observed_at: string | null;
}

export interface SourceStatus {
  code: string;
  name: string;
  kind: string;
  enabled: boolean;
  state: "ok" | "stale" | "disabled" | "needs_credentials";
  last_success_at: string | null;
  last_error: string | null;
  licence: string | null;
}

export interface Warning {
  id: string;
  station_id: number;
  station_name: string;
  district: string | null;
  level: Exclude<RiskLevel, "NORMAL" | "UNKNOWN">;
  status: string;
  source: string;
  exercise: boolean;
  confidence: string;
  message: { en: string; ne: string };
  reasons: string[];
  approvers: string[];
  created_at: string;
  valid_until: string | null;
}

export interface Profile {
  country_code: string;
  name: string;
  timezone: string;
  languages: string[];
  bbox: [number, number, number, number];
  hydromet_authority: string;
  drr_authority: string;
  policies: { exercise_mode?: boolean };
}

export interface Shelter {
  id: number; name: string; name_local: string | null; district: string | null; lat: number; lon: number;
  capacity: number; occupancy: number; free_places: number; status: "open" | "full" | "closed" | "unsafe";
  accessible: boolean; accepts_livestock: boolean; has_medical: boolean; contact: string | null; updated_at: string; distance_km?: number | null;
}
