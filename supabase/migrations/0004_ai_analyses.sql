-- AI analyst runs: advisory findings produced by an LLM agent from the live data (never warnings themselves)
create table if not exists ai_analyses (
  id             uuid primary key default gen_random_uuid(),
  trigger        text not null check (trigger in ('auto', 'manual')),
  requested_by   text,
  status         text not null check (status in ('running', 'done', 'failed')),
  model          text not null,
  started_at     timestamptz not null default now(),
  finished_at    timestamptz,
  overall_level  text check (overall_level in ('NORMAL', 'WATCH', 'WARNING', 'CRITICAL')),
  headline       text,
  summary        text,
  findings       jsonb not null default '[]'::jsonb,
  data_gaps      jsonb not null default '[]'::jsonb,
  tool_calls     integer not null default 0,
  input_tokens   integer not null default 0,
  output_tokens  integer not null default 0,
  error          text
);
create index if not exists ai_analyses_recent_idx on ai_analyses (started_at desc);
