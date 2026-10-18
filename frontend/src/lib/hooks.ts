"use client";

import useSWR from "swr";

import { fetcher, type FC, type GridProps, type SourceStatus, type StationProps, type Warning, type WeatherSummary } from "./api";

const POLL = { refreshInterval: 60_000 };

export function useRivers() { return useSWR<FC<StationProps>>("/api/v1/stations?kind=river", fetcher, POLL); }
export function useRain() { return useSWR<FC<StationProps>>("/api/v1/stations?kind=rain", fetcher, POLL); }
export function useStatus() { return useSWR<SourceStatus[]>("/api/v1/status", fetcher, POLL); }
export function useWarnings(status?: string) {
  return useSWR<Warning[]>(`/api/v1/warnings${status ? `?status=${status}` : ""}`, fetcher, POLL);
}
export function useWeatherSummary() { return useSWR<WeatherSummary>("/api/v1/weather/summary", fetcher, POLL); }

/** Everything the 3D map needs. */
export function useMapData() {
  const { data: nepalGrid } = useSWR<FC<GridProps>>("/api/v1/weather/grid?grid=nepal", fetcher, POLL);
  const { data: globalGrid } = useSWR<FC<GridProps>>("/api/v1/weather/grid?grid=global", fetcher, POLL);
  const { data: satelliteGrid } = useSWR<FC<GridProps>>("/api/v1/weather/grid?grid=imerg_nepal", fetcher, POLL);
  const { data: rivers } = useRivers();
  const { data: rain } = useRain();
  return { nepalGrid, globalGrid, satelliteGrid, rivers, rain };
}
