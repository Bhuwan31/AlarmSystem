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

    # AI analyst / assistant (Claude). Needs ANTHROPIC_API_KEY in the environment; off without it.
    ai_enabled: bool = True
    ai_provider: str = "auto"            # auto | anthropic | gemini | openai_compat
    ai_model: str = ""                   # empty = provider default
    ai_fallback_model: str = ""          # used when the main model is overloaded; empty = provider default
                                         # (Gemini: gemini-flash-lite-latest), "off" = no fallback
    gemini_api_key: str = ""             # free tier: https://aistudio.google.com/apikey
    ai_base_url: str = ""                # openai_compat only, e.g. https://api.groq.com/openai/v1/
    ai_api_key: str = ""                 # openai_compat only
    ai_effort: str = "medium"            # analyst: low | medium | high | xhigh | max
    ai_chat_effort: str = "medium"
    ai_interval_s: int = 0               # 0 = provider default (30 min Claude, 3 h Gemini free tier)
    ai_max_iterations: int = 20
    ai_propose_messages: bool = True      # turn WATCH+ AI findings into draft area messages for approvers
    ai_chat_per_hour: int = 30           # per user

    # AI visual disaster detection (photos)
    visual_storage_dir: str = "/data/visual"     # private image store (docker volume); never served directly
    visual_max_upload_mb: int = 10
    visual_uploads_per_hour: int = 20            # per user
    visual_group_km: float = 2.0                 # photos closer than this (and within visual_group_hours) join one incident
    visual_group_hours: float = 6.0
    allow_self_registration: bool = True         # citizens can create viewer accounts to report photos / receive alerts

    # Notifications. External channels stay SIMULATED (logged, not sent) until notify_external_enabled=true.
    notify_external_enabled: bool = False
    notify_max_per_day: int = 10                 # per recipient, non-CRITICAL; CRITICAL is never rate-limited
    notify_cooldown_min: int = 30                # same incident, same or lower level → suppressed within this window
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    twilio_account_sid: str = ""                 # SMS via Twilio's REST API
    twilio_auth_token: str = ""
    twilio_from: str = ""
    ntfy_server: str = "https://ntfy.sh"   # phone alerts via the ntfy app; or your own ntfy server
    ntfy_token: str = ""                   # only for a protected/self-hosted ntfy server
    public_app_url: str = ""               # link opened when a phone notification is tapped (optional)
    vapid_public_key: str = ""                   # Web Push (needs the pywebpush package)
    vapid_private_key: str = ""
    vapid_subject: str = ""

    # First admin account, created at startup only if no users exist yet
    admin_email: str = ""
    admin_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
