import type { RiskLevel } from "./api";
import { RAMPS, type Ramp } from "./field";

export type LayerKey =
  | "temperature" | "heat" | "humidity" | "rainForecast" | "cloud"
  | "windFlow" | "windArrows"
  | "riversWorld" | "riversNepal" | "riverGauges" | "rainGauges" | "satellite"
  | "terrain" | "border";

export type Layers = Record<LayerKey, boolean>;

export interface Filters {
  riskLevels: RiskLevel[];
  minWindKmh: number;
  minRain24h: number;
  transboundaryOnly: boolean;
}

export interface LayerInfo {
  key: LayerKey;
  group: "Weather" | "Wind" | "Water" | "Terrain & borders";
  label: string;
  description: string;
  source: string;
  updates: string;
  ramp?: Ramp;
  rampUnit?: string;
}

export const LAYER_INFO: LayerInfo[] = [
  { key: "temperature", group: "Weather", label: "Temperature", ramp: RAMPS.temperature, rampUnit: "°C",
    description: "Air temperature 2 m above ground, interpolated into a continuous field. Nepal uses a 0.5° grid, the rest of the world a 10° grid.",
    source: "Open-Meteo (CC BY 4.0)", updates: "Nepal hourly, world every 3 h" },
  { key: "heat", group: "Weather", label: "Heatwave risk", ramp: RAMPS.heat, rampUnit: "°C max, next 3 days",
    description: "Areas where the maximum temperature in the next 3 days reaches 32 °C or more. Click a place for its heat status and advice.",
    source: "Open-Meteo forecast", updates: "With temperature" },
  { key: "humidity", group: "Weather", label: "Humidity", ramp: RAMPS.humidity, rampUnit: "%",
    description: "Relative humidity at 2 m.", source: "Open-Meteo", updates: "With temperature" },
  { key: "rainForecast", group: "Weather", label: "Rain forecast (24 h)", ramp: RAMPS.rain, rampUnit: "mm",
    description: "Total rainfall expected in the next 24 hours.", source: "Open-Meteo forecast", updates: "With temperature" },
  { key: "cloud", group: "Weather", label: "Cloud cover", ramp: RAMPS.cloud, rampUnit: "%",
    description: "Share of the sky covered by cloud.", source: "Open-Meteo", updates: "With temperature" },
  { key: "windFlow", group: "Wind", label: "Wind flow (animated)",
    description: "Moving streaks follow the surface wind (10 m). Colour shows speed: blue light, purple strong, red very strong. Use the filter to show only stronger winds.",
    source: "Open-Meteo", updates: "With temperature" },
  { key: "windArrows", group: "Wind", label: "Wind arrows",
    description: "Arrow per grid cell pointing where the wind blows to; size grows with speed.", source: "Open-Meteo", updates: "With temperature" },
  { key: "riversWorld", group: "Water", label: "World rivers",
    description: "Major rivers worldwide.", source: "Natural Earth (public domain)", updates: "Static" },
  { key: "riversNepal", group: "Water", label: "Nepal rivers (incl. cross-border)",
    description: "Every named river flowing through Nepal, including its stretches in China and India. Purple = crosses a border. Click a river to see the countries it flows through.",
    source: "© OpenStreetMap contributors (ODbL)", updates: "Static, rebuilt with scripts/build_rivers.py" },
  { key: "riverGauges", group: "Water", label: "River gauges (3D)",
    description: "Live DHM river-level stations. Column height = how close the river is to its warning level; colour = risk level from the rules engine.",
    source: "DHM Nepal live feed", updates: "Every 5 min" },
  { key: "rainGauges", group: "Water", label: "Rain gauges (3D)",
    description: "Live DHM rain stations. Column height = rainfall in the last 24 h.", source: "DHM Nepal live feed", updates: "Every 5 min" },
  { key: "satellite", group: "Water", label: "Satellite rain",
    description: "Rain rate from NASA GPM IMERG / INSAT (shown once credentials are configured).", source: "NASA, ISRO MOSDAC", updates: "Every 30 min" },
  { key: "terrain", group: "Terrain & borders", label: "3D terrain",
    description: "Real elevation, so mountains and valleys appear in 3D when you tilt or zoom in.", source: "AWS Terrain Tiles (Mapzen, open data)", updates: "Static" },
  { key: "border", group: "Terrain & borders", label: "Nepal border", description: "Outline of the deployment country.", source: "Natural Earth", updates: "Static" },
];

export const DEFAULT_LAYERS: Layers = {
  temperature: true, heat: false, humidity: false, rainForecast: false, cloud: false,
  windFlow: true, windArrows: false,
  riversWorld: true, riversNepal: true, riverGauges: true, rainGauges: false, satellite: true,
  terrain: true, border: true,
};

export const MINI_LAYERS: Layers = {
  ...DEFAULT_LAYERS, riverGauges: false, rainGauges: false, satellite: false, terrain: false, riversWorld: true,
};

export const DEFAULT_FILTERS: Filters = {
  riskLevels: ["NORMAL", "WATCH", "WARNING", "CRITICAL", "UNKNOWN"],
  minWindKmh: 0,
  minRain24h: 0,
  transboundaryOnly: false,
};
