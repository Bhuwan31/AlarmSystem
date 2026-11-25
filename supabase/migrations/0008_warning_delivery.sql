-- Approved warnings reach residents: activating a warning creates an area message around its station (source 'warning'),
-- and cancelling it sends an all-clear to the same area. Both are recorded like any other area message.
alter table area_broadcasts drop constraint if exists area_broadcasts_source_check;
alter table area_broadcasts add constraint area_broadcasts_source_check check (source in ('operator', 'ai_analyst', 'warning'));
alter table area_broadcasts add column if not exists warning_id uuid references warnings(id) on delete set null;
alter table area_broadcasts add column if not exists all_clear  boolean not null default false;
create index if not exists area_broadcasts_warning_idx on area_broadcasts (warning_id);
