-- AMHEWS core schema. Runs on Supabase or any PostgreSQL 15+ with PostGIS.
create extension if not exists postgis;
create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Deployment profile and data sources (FR-63..FR-68)
-- ---------------------------------------------------------------------------
create table if not exists deployment_profile (
  id              smallint primary key default 1 check (id = 1),
  country_code    text not null,
  name            text not null,
  timezone        text not null,
  languages       text[] not null,
  bbox            double precision[] not null,          -- [min_lon, min_lat, max_lon, max_lat]
  hydromet_authority text,
  drr_authority   text,
  emergency_numbers jsonb not null default '{}'::jsonb,
  policies        jsonb not null default '{}'::jsonb,   -- auto_publish_watch, critical_timeout_s, watch_fraction ...
  updated_at      timestamptz not null default now()
);

create table if not exists data_sources (
  code            text primary key,                      -- 'dhm_river', 'dhm_rain', 'open_meteo', 'gpm_imerg', 'insat', 'device'
  name            text not null,
  kind            text not null,                         -- gauge | satellite | model | device
  poll_seconds    integer not null,
  staleness_seconds integer not null,
  licence         text,
  enabled         boolean not null default true,
  last_success_at timestamptz,
  last_error      text,
  last_error_at   timestamptz
);

-- ---------------------------------------------------------------------------
-- Stations (government gauges and own devices share one table)
-- ---------------------------------------------------------------------------
create table if not exists stations (
  id              bigserial primary key,
  source_code     text not null references data_sources(code),
  external_id     text not null,
  kind            text not null check (kind in ('river', 'rain', 'device_river', 'device_rain')),
  name            text not null,
  basin           text,
  district        text,
  geom            geometry(Point, 4326) not null,
  elevation_m     double precision,
  watch_level     double precision,
  warning_level   double precision,
  danger_level    double precision,
  meta            jsonb not null default '{}'::jsonb,
  updated_at      timestamptz not null default now(),
  unique (source_code, external_id)
);
create index if not exists stations_geom_idx on stations using gist (geom);

create table if not exists observations (
  id              bigserial primary key,
  station_id      bigint not null references stations(id) on delete cascade,
  variable        text not null,                         -- water_level_m | rain_1h_mm | rain_24h_mm ...
  value           double precision,
  unit            text not null,
  observed_at     timestamptz not null,
  received_at     timestamptz not null default now(),
  quality         text not null check (quality in ('GOOD', 'SUSPECT', 'BAD', 'MISSING')),
  quality_reason  text,
  is_simulated    boolean not null default false,
  raw             jsonb not null,
  unique (station_id, variable, observed_at)
);
create index if not exists observations_station_time_idx on observations (station_id, variable, observed_at desc);

-- Weather grid snapshots (Open-Meteo, satellite rainfall), one row per grid point per run
create table if not exists weather_grid (
  id              bigserial primary key,
  grid            text not null,                         -- 'nepal' | 'global' | 'imerg_nepal' | 'insat_nepal'
  source_code     text not null references data_sources(code),
  lat             double precision not null,
  lon             double precision not null,
  observed_at     timestamptz not null,
  temperature_c   double precision,
  humidity_pct    double precision,
  precipitation_mm double precision,
  rain_24h_forecast_mm double precision,
  wind_speed_kmh  double precision,
  wind_dir_deg    double precision,
  wind_gust_kmh   double precision,
  cloud_cover_pct double precision,
  weather_code    integer,
  received_at     timestamptz not null default now()
);
create index if not exists weather_grid_latest_idx on weather_grid (grid, observed_at desc);

create table if not exists data_quality_events (
  id              bigserial primary key,
  source_code     text references data_sources(code),
  station_id      bigint references stations(id) on delete cascade,
  kind            text not null check (kind in ('missing', 'stale', 'spike', 'flatline', 'range', 'conflict', 'device_fault')),
  detail          jsonb not null default '{}'::jsonb,
  opened_at       timestamptz not null default now(),
  closed_at       timestamptz
);
create unique index if not exists dq_open_unique on data_quality_events (coalesce(station_id, 0), coalesce(source_code, ''), kind) where closed_at is null;

-- ---------------------------------------------------------------------------
-- Risk and warnings (FR-11..FR-29, SR-01..SR-12)
-- ---------------------------------------------------------------------------
create table if not exists risk_assessments (
  id              bigserial primary key,
  station_id      bigint not null references stations(id) on delete cascade,
  hazard          text not null default 'FLOOD',
  level           text not null check (level in ('NORMAL', 'WATCH', 'WARNING', 'CRITICAL', 'UNKNOWN')),
  confidence      text not null check (confidence in ('HIGH', 'MEDIUM', 'LOW')),
  reasons         jsonb not null,
  inputs          jsonb not null,
  engine_version  text not null,
  computed_at     timestamptz not null default now()
);
create index if not exists risk_latest_idx on risk_assessments (station_id, computed_at desc);

create table if not exists warnings (
  id              uuid primary key default gen_random_uuid(),
  series_id       uuid not null default gen_random_uuid(),
  version         integer not null default 1,
  station_id      bigint not null references stations(id),
  hazard          text not null default 'FLOOD',
  level           text not null check (level in ('WATCH', 'WARNING', 'CRITICAL')),
  status          text not null check (status in ('PROPOSED', 'ACTIVE', 'REJECTED', 'CANCELLED', 'EXPIRED', 'SUPERSEDED')),
  source          text not null check (source in ('auto', 'manual', 'official_import')),
  exercise        boolean not null default false,
  confidence      text not null,
  message         jsonb not null,                        -- { "en": "...", "ne": "..." }
  reasons         jsonb not null default '[]'::jsonb,
  proposed_by     text not null,
  rejection_reason text,
  cancel_reason   text,
  valid_from      timestamptz,
  valid_until     timestamptz,
  supersedes      uuid references warnings(id),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
-- INV-1: at most one ACTIVE warning per station reach and hazard
create unique index if not exists one_active_warning on warnings (station_id, hazard) where status = 'ACTIVE';
-- at most one open proposal per station reach and hazard
create unique index if not exists one_open_proposal on warnings (station_id, hazard) where status = 'PROPOSED';

create table if not exists warning_approvals (
  warning_id      uuid not null references warnings(id) on delete cascade,
  approver        text not null,
  approved_at     timestamptz not null default now(),
  primary key (warning_id, approver)
);

-- ---------------------------------------------------------------------------
-- Field devices and sirens (FR-69..FR-75, SR-13, SR-14)
-- ---------------------------------------------------------------------------
create table if not exists devices (
  id              text primary key,                      -- e.g. 'gauge-001', 'siren-001'
  kind            text not null check (kind in ('gauge', 'siren')),
  name            text not null,
  geom            geometry(Point, 4326) not null,
  station_id      bigint references stations(id),        -- gauge: its own station row; siren: the reach it covers
  secret_hash     text not null,                         -- sha256 of the device secret; secret itself never stored
  firmware        text,
  battery_v       double precision,
  rssi_dbm        double precision,
  last_seen_at    timestamptz,
  status          text not null default 'unknown' check (status in ('ok', 'degraded', 'offline', 'unknown')),
  test_mode       boolean not null default true,
  created_at      timestamptz not null default now()
);

create table if not exists siren_commands (
  id              uuid primary key default gen_random_uuid(),
  device_id       text not null references devices(id),
  warning_id      uuid references warnings(id),
  command         text not null check (command in ('activate', 'stop', 'self_test')),
  test_mode       boolean not null,
  nonce           text not null unique,
  signature       text not null,
  issued_by       text not null,
  issued_at       timestamptz not null default now(),
  acked_at        timestamptz,
  ack_payload     jsonb
);

-- ---------------------------------------------------------------------------
-- Audit log (FR-59): append-only, hash-chained
-- ---------------------------------------------------------------------------
create table if not exists audit_log (
  id              bigserial primary key,
  at              timestamptz not null default now(),
  actor           text not null,
  action          text not null,
  entity          text not null,
  entity_id       text,
  payload         jsonb not null default '{}'::jsonb,
  prev_hash       text,
  hash            text not null
);

create or replace function audit_log_chain() returns trigger language plpgsql as $$
declare last_hash text;
begin
  perform pg_advisory_xact_lock(4242);
  select hash into last_hash from audit_log order by id desc limit 1;
  new.prev_hash := last_hash;
  new.hash := encode(digest(coalesce(last_hash, '') || new.at::text || new.actor || new.action || new.entity
                            || coalesce(new.entity_id, '') || new.payload::text, 'sha256'), 'hex');
  return new;
end $$;
drop trigger if exists audit_log_chain_trg on audit_log;
create trigger audit_log_chain_trg before insert on audit_log for each row execute function audit_log_chain();

create or replace function audit_log_immutable() returns trigger language plpgsql as $$
begin
  raise exception 'audit_log is append-only';
end $$;
drop trigger if exists audit_log_no_update on audit_log;
create trigger audit_log_no_update before update or delete on audit_log for each row execute function audit_log_immutable();

-- ---------------------------------------------------------------------------
-- Seed: data sources and the Nepal deployment profile (first deployment)
-- ---------------------------------------------------------------------------
insert into data_sources (code, name, kind, poll_seconds, staleness_seconds, licence, enabled) values
  ('dhm_river',  'DHM river-level stations (Nepal)',      'gauge',     300,  3600, 'DHM — use requires data-sharing agreement for production', true),
  ('dhm_rain',   'DHM rainfall stations (Nepal)',         'gauge',     600,  7200, 'DHM — use requires data-sharing agreement for production', true),
  ('open_meteo', 'Open-Meteo weather (model + obs)',      'model',    3600, 10800, 'CC BY 4.0, non-commercial free tier', true),
  ('gpm_imerg',  'NASA GPM IMERG Early (satellite rain)', 'satellite', 1800, 21600, 'NASA open data; Earthdata login required', false),
  ('insat',      'INSAT-3D/3DR/3DS via MOSDAC',           'satellite',  900,  7200, 'ISRO MOSDAC; registered account required', false),
  ('device',     'Own field devices (MQTT)',              'device',     60,   600, 'Project-owned', true)
on conflict (code) do nothing;

insert into deployment_profile (id, country_code, name, timezone, languages, bbox, hydromet_authority, drr_authority, emergency_numbers, policies)
values (1, 'NP', 'Nepal (first deployment)', 'Asia/Kathmandu', array['ne', 'en'], array[80.0, 26.3, 88.3, 30.5],
        'Department of Hydrology and Meteorology (DHM)', 'National Disaster Risk Reduction and Management Authority (NDRRMA)',
        '{"police": "100", "fire": "101", "ambulance": "102"}'::jsonb,
        '{"auto_publish_watch": false, "critical_timeout_s": 600, "watch_fraction": 0.8, "watch_margin_m": 1.0, "rise_rate_m_per_h": 0.5, "hold_minutes": 60, "exercise_mode": true}'::jsonb)
on conflict (id) do nothing;
