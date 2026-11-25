-- The message residents receive for a warning: written by the AI from the station's data, editable by the operator,
-- and sent exactly as shown when the warning is approved. Falls back to the fixed template when no AI is available.
alter table warnings add column if not exists resident_title          text;
alter table warnings add column if not exists resident_message        text;
alter table warnings add column if not exists resident_message_source text check (resident_message_source in ('ai', 'template', 'edited'));
alter table warnings add column if not exists resident_message_model  text;
alter table warnings add column if not exists resident_message_at     timestamptz;
