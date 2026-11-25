-- AI visual disaster detection: photo observations, model predictions, incidents, location-aware notifications,
-- area broadcasts and model training runs. Additive only (no existing table is changed).
--
-- Safety model: the models only PROPOSE. A person with the approver role reviews every incident and the suggested
-- message before any notification leaves the system (see app/vision/policy.py and app/api/visual.py).

-- Citizens' consent and home location for location-based alerts. One row per user account; no row = no alerts.
create table if not exists alert_subscriptions (
  user_id          uuid primary key references users(id) on delete cascade,
  consent          boolean not null default false,
  consent_at       timestamptz,
  opted_out_at     timestamptz,
  home             geometry(Point, 4326),
  home_label       text,
  district         text,
  province         text,
  channels         jsonb not null default '{"in_app": true, "push": false, "sms": false, "email": false}'::jsonb,
  phone            text,
  email            text,
  updated_at       timestamptz not null default now()
);
create index if not exists alert_subscriptions_home_idx on alert_subscriptions using gist (home);
create index if not exists alert_subscriptions_district_idx on alert_subscriptions (lower(district));
create index if not exists alert_subscriptions_province_idx on alert_subscriptions (lower(province));

-- Browser Web Push endpoints (used only when VAPID keys are configured)
create table if not exists push_subscriptions (
  id               bigserial primary key,
  user_id          uuid not null references users(id) on delete cascade,
  endpoint         text not null unique,
  p256dh           text not null,
  auth             text not null,
  created_at       timestamptz not null default now()
);

create table if not exists visual_observations (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid references users(id) on delete set null,
  image_reference     text not null,                 -- private path under VISUAL_STORAGE_DIR (never served directly)
  preview_reference   text not null,                 -- re-encoded copy without EXIF, for reviewers
  sha256              text not null,
  dhash               text not null,                 -- 64-bit perceptual hash (hex), for near-duplicate detection
  mime_type           text not null,
  width               integer not null,
  height              integer not null,
  bytes               integer not null,
  capture_timestamp   timestamptz,                   -- when the photo was taken (camera clock or EXIF), if known
  capture_tz_offset_min integer,                 -- the photo's own UTC offset, so the local time is shown as recorded
  capture_time_source text not null check (capture_time_source in ('device_clock', 'exif', 'exif_assumed_tz', 'unknown')),
  upload_timestamp    timestamptz not null default now(),
  latitude            double precision,
  longitude           double precision,
  geom                geometry(Point, 4326),
  gps_accuracy        double precision,              -- metres; null = unknown
  location_source     text check (location_source in ('device_gps', 'exif', 'manual')),
  image_source        text not null check (image_source in ('camera', 'upload')),
  exif                jsonb not null default '{}'::jsonb,   -- extracted metadata (only time, GPS, camera make/model)
  duplicate_of        uuid references visual_observations(id),
  processing_status   text not null default 'awaiting_location'
                      check (processing_status in ('awaiting_location', 'received', 'queued', 'processing', 'done', 'failed', 'rejected')),
  error               text,
  incident_id         uuid,
  created_at          timestamptz not null default now()
);
create index if not exists visual_observations_geom_idx on visual_observations using gist (geom);
create index if not exists visual_observations_recent_idx on visual_observations (created_at desc);
create index if not exists visual_observations_sha_idx on visual_observations (sha256);
create index if not exists visual_observations_user_idx on visual_observations (user_id, created_at desc);

create table if not exists ai_predictions (
  id                  uuid primary key default gen_random_uuid(),
  observation_id      uuid not null references visual_observations(id) on delete cascade,
  predicted_class     text not null,
  class_probabilities jsonb not null,
  visual_confidence   double precision not null,
  dqn_action          text,                          -- the decision agent's advice (null when the agent is unavailable)
  dqn_q_values        jsonb,
  policy_action       text not null,                 -- what the independent safety policy allows
  risk_level          text not null check (risk_level in ('LOW', 'MODERATE', 'HIGH', 'SEVERE')),
  alert_level         text not null check (alert_level in ('NONE', 'WATCH', 'WARNING', 'CRITICAL')),
  alert_eligible      boolean not null,
  weather_correlation text not null,
  evidence            jsonb not null default '{}'::jsonb,   -- weather, rivers, history, reliability checks
  reasons             jsonb not null default '[]'::jsonb,
  model_version       text not null,
  inference_timestamp timestamptz not null default now()
);
create index if not exists ai_predictions_obs_idx on ai_predictions (observation_id);

create table if not exists disaster_incidents (
  id                   uuid primary key default gen_random_uuid(),
  disaster_type        text not null,
  incident_status      text not null default 'PROPOSED'
                       check (incident_status in ('PROPOSED', 'ACTIVE', 'CLOSED', 'REJECTED')),
  latitude             double precision not null,
  longitude            double precision not null,
  geom                 geometry(Point, 4326) not null,
  location_label       text,
  district             text,
  province             text,
  affected_radius      double precision not null,     -- km
  suggested_radius     double precision not null,     -- km, from the policy
  risk_level           text not null check (risk_level in ('LOW', 'MODERATE', 'HIGH', 'SEVERE')),
  alert_level          text not null check (alert_level in ('WATCH', 'WARNING', 'CRITICAL')),
  suggested_level      text not null check (suggested_level in ('WATCH', 'WARNING', 'CRITICAL')),
  report_count         integer not null default 1,
  max_confidence       double precision not null default 0,
  weather_correlation  text not null default 'unavailable',
  proposed_message     jsonb not null,                -- {"title": ..., "body": ...}
  sent_message         jsonb,
  verification_status  text not null default 'unverified' check (verification_status in ('unverified', 'confirmed', 'rejected')),
  verified_by          text,
  verified_at          timestamptz,
  approved_by          text,
  approved_at          timestamptz,
  closed_by            text,
  closed_at            timestamptz,
  close_note           text,
  exercise             boolean not null default true,
  first_detected_at    timestamptz not null default now(),
  last_updated_at      timestamptz not null default now()
);
create index if not exists disaster_incidents_geom_idx on disaster_incidents using gist (geom);
create index if not exists disaster_incidents_open_idx on disaster_incidents (incident_status, last_updated_at desc);

do $$ begin
  alter table visual_observations add constraint visual_observations_incident_fk
    foreign key (incident_id) references disaster_incidents(id) on delete set null;
exception when duplicate_object then null; end $$;

-- Admin-composed messages to an area: whole country, a province, a district, a city or a map point + radius
create table if not exists area_broadcasts (
  id               uuid primary key default gen_random_uuid(),
  target_type      text not null check (target_type in ('country', 'province', 'district', 'city', 'point')),
  target_value     text,                              -- province / district / city name; null for country / point
  center           geometry(Point, 4326),             -- city / point targets
  radius_km        double precision,
  level            text not null check (level in ('INFO', 'WATCH', 'WARNING', 'CRITICAL')),
  title            text not null,
  message          text not null,
  send_at          timestamptz not null,
  valid_until      timestamptz,
  status           text not null default 'SCHEDULED' check (status in ('SCHEDULED', 'SENDING', 'SENT', 'CANCELLED', 'FAILED')),
  exercise         boolean not null default true,
  recipients       integer,
  created_by       text not null,
  created_at       timestamptz not null default now(),
  sent_at          timestamptz,
  cancelled_by     text,
  error            text
);
create index if not exists area_broadcasts_due_idx on area_broadcasts (status, send_at);

create table if not exists emergency_notifications (
  id                   uuid primary key default gen_random_uuid(),
  incident_id          uuid references disaster_incidents(id) on delete cascade,
  broadcast_id         uuid references area_broadcasts(id) on delete cascade,
  recipient_id         uuid not null references users(id) on delete cascade,
  notification_channel text not null check (notification_channel in ('in_app', 'push', 'sms', 'email')),
  notification_status  text not null check (notification_status in ('queued', 'delivered', 'sent', 'simulated', 'failed', 'skipped_unconfigured', 'suppressed')),
  level                text not null,
  title                text not null,
  body                 text not null,
  distance_km          double precision,
  error                text,
  created_at           timestamptz not null default now(),
  sent_at              timestamptz,
  read_at              timestamptz,
  acknowledged_at      timestamptz,
  check (incident_id is not null or broadcast_id is not null)
);
-- Deduplication: one notification per recipient, channel and level for an incident; one per recipient and channel per broadcast
create unique index if not exists emergency_notifications_incident_dedup
  on emergency_notifications (incident_id, recipient_id, notification_channel, level) where incident_id is not null;
create unique index if not exists emergency_notifications_broadcast_dedup
  on emergency_notifications (broadcast_id, recipient_id, notification_channel) where broadcast_id is not null;
create index if not exists emergency_notifications_inbox_idx on emergency_notifications (recipient_id, created_at desc);

create table if not exists model_training_runs (
  id                   uuid primary key default gen_random_uuid(),
  model_name           text not null,                 -- 'visual_cnn' | 'visual_dqn'
  model_version        text not null,
  dataset_version      text not null,
  training_parameters  jsonb not null,
  validation_metrics   jsonb not null,
  test_metrics         jsonb not null,
  checkpoint_reference text not null,
  validated_for_alerts boolean not null default false,
  created_at           timestamptz not null default now(),
  unique (model_name, model_version)
);
