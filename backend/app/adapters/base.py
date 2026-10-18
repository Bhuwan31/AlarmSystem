from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class StationRecord:
    """A gauge as reported by a source; upserted into `stations`."""
    source_code: str
    external_id: str
    kind: str                      # river | rain | device_river | device_rain
    name: str
    lat: float
    lon: float
    basin: str | None = None
    district: str | None = None
    elevation_m: float | None = None
    warning_level: float | None = None
    danger_level: float | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class ObservationRecord:
    source_code: str
    external_id: str
    variable: str                  # water_level_m | rain_1h_mm | rain_24h_mm
    value: float | None
    unit: str
    observed_at: datetime
    raw: dict
    is_simulated: bool = False


@dataclass
class GridPoint:
    lat: float
    lon: float
    observed_at: datetime
    temperature_c: float | None = None
    humidity_pct: float | None = None
    precipitation_mm: float | None = None
    rain_24h_forecast_mm: float | None = None
    wind_speed_kmh: float | None = None
    wind_dir_deg: float | None = None
    wind_gust_kmh: float | None = None
    cloud_cover_pct: float | None = None
    weather_code: int | None = None
    apparent_temp_c: float | None = None
    pressure_hpa: float | None = None
    tmax_3d_c: float | None = None


class AdapterDisabled(Exception):
    """Raised when an adapter lacks the credentials or files it needs."""
