-- Operator accounts (local auth; tokens are Supabase-compatible so Supabase Auth can replace this later)
create table if not exists users (
  id              uuid primary key default gen_random_uuid(),
  email           text not null unique,
  name            text not null,
  role            text not null check (role in ('viewer', 'operator', 'approver', 'admin')),
  password_hash   text not null,                 -- scrypt$<salt-hex>$<hash-hex>
  totp_secret     text,                          -- base32; null = MFA not enrolled
  totp_pending    text,                          -- secret awaiting first verification
  active          boolean not null default true,
  created_at      timestamptz not null default now(),
  last_login_at   timestamptz
);

-- Evacuation shelters (FR-38..FR-40, FR-55, SR-05)
create table if not exists shelters (
  id                bigserial primary key,
  name              text not null,
  name_local        text,
  district          text,
  geom              geometry(Point, 4326) not null,
  capacity          integer not null check (capacity >= 0),
  occupancy         integer not null default 0 check (occupancy >= 0),
  status            text not null default 'open' check (status in ('open', 'full', 'closed', 'unsafe')),
  accessible        boolean not null default false,
  accepts_livestock boolean not null default false,
  has_medical       boolean not null default false,
  contact           text,
  updated_at        timestamptz not null default now(),
  updated_by        text
);
create index if not exists shelters_geom_idx on shelters using gist (geom);
