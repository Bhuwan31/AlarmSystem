from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://amhews:amhews@localhost:5432/amhews"
    cors_origins: str = "http://localhost:3000"

    # Supabase-compatible JWT verification for operator endpoints (HS256 project secret)
    jwt_secret: str = "change-me-dev-only-secret-at-least-32-chars"
    jwt_audience: str = "authenticated"

    # Scheduler: set false to run the API without background ingestion (tests, read-only replicas)
    enable_scheduler: bool = True

    # Open-Meteo grids
    nepal_grid_step_deg: float = 0.5
    global_grid_step_deg: float = 10.0
    nepal_weather_poll_s: int = 3600
    global_weather_poll_s: int = 10800

    # DHM public socket feed
    dhm_base_url: str = "https://www.hydrology.gov.np"
    dhm_socket_path: str = "/gss/socket.io"
    dhm_poll_s: int = 300

    # NASA GPM IMERG Early (needs an Earthdata bearer token)
    earthdata_token: str = ""
    imerg_product: str = "GPM_3IMERGHHE.07"
    imerg_version_tag: str = "V07B"
    imerg_poll_s: int = 1800

    # INSAT via MOSDAC: files downloaded by MOSDAC's official download tool land in this folder
    insat_inbox_dir: str = ""
    insat_rain_dataset: str = "HEM"
    insat_lat_dataset: str = "Latitude"
    insat_lon_dataset: str = "Longitude"
    insat_poll_s: int = 900

    # Field devices
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    siren_signing_key: str = "change-me-siren-signing-key"

    # First admin account, created at startup only if no users exist yet
    admin_email: str = ""
    admin_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
