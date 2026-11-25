-- "Send to all phones": every message that is actually sent (warning, all-clear, area message, photo incident) is
-- also published once to a mass channel. Today that is one ntfy topic (MASS_ALERT_NTFY_TOPIC); later it can be cell
-- broadcast to every phone in the area. One row per message, level and all-clear, so a re-send never repeats it.
create table if not exists mass_alerts (
  id          uuid primary key default gen_random_uuid(),
  ref         text not null,                 -- 'broadcast:<id>' or 'incident:<id>'
  level       text not null,
  all_clear   boolean not null default false,
  channel     text not null,                 -- 'ntfy' today; 'cell_broadcast' later
  status      text not null check (status in ('sent', 'simulated', 'failed', 'skipped_unconfigured')),
  error       text,
  title       text not null,
  body        text not null,
  created_at  timestamptz not null default now(),
  unique (ref, level, all_clear)
);
alter table mass_alerts enable row level security;    -- not reachable through Supabase's public Data API
