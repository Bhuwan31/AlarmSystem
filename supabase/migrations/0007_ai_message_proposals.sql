-- AI-suggested area messages. The AI analyst drafts a message for a risk area (status PROPOSED); an approver edits it,
-- then sends it (SCHEDULED -> SENT) or rejects it (REJECTED, kept for the record and can still be sent later).
alter table area_broadcasts drop constraint if exists area_broadcasts_status_check;
alter table area_broadcasts add constraint area_broadcasts_status_check
  check (status in ('PROPOSED', 'SCHEDULED', 'SENDING', 'SENT', 'CANCELLED', 'FAILED', 'REJECTED'));

alter table area_broadcasts add column if not exists source text not null default 'operator';
alter table area_broadcasts drop constraint if exists area_broadcasts_source_check;
alter table area_broadcasts add constraint area_broadcasts_source_check check (source in ('operator', 'ai_analyst'));
alter table area_broadcasts add column if not exists area_label        text;          -- place name shown to approvers
alter table area_broadcasts add column if not exists hazard            text;
alter table area_broadcasts add column if not exists ai_analysis_id    uuid references ai_analyses(id) on delete set null;
alter table area_broadcasts add column if not exists ai_reason         jsonb;         -- what the AI saw: summary, evidence, confidence
alter table area_broadcasts add column if not exists original_level    text;          -- the AI's draft, kept when an approver edits
alter table area_broadcasts add column if not exists original_title    text;
alter table area_broadcasts add column if not exists original_message  text;
alter table area_broadcasts add column if not exists original_radius_km double precision;
alter table area_broadcasts add column if not exists reviewed_by       text;
alter table area_broadcasts add column if not exists reviewed_at       timestamptz;
alter table area_broadcasts add column if not exists review_note       text;
alter table area_broadcasts add column if not exists updated_at        timestamptz;

create index if not exists area_broadcasts_proposed_idx on area_broadcasts (created_at desc) where status = 'PROPOSED';
