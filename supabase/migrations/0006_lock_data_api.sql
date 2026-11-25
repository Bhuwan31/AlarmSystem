-- Keep every AMHEWS table away from Supabase's public Data API (REST/GraphQL with the anon key).
-- The backend connects directly as the table owner, which bypasses row level security, so it is unaffected.
-- No-op for the parts that do not apply on a plain PostgreSQL server (no anon/authenticated roles).
do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' and tableowner = current_user and tablename <> 'spatial_ref_sys' loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;
  if exists (select 1 from pg_roles where rolname = 'anon') and exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'revoke all on all tables in schema public from anon, authenticated';
    execute 'revoke all on all sequences in schema public from anon, authenticated';
    execute 'revoke all on all functions in schema public from anon, authenticated';
    execute 'alter default privileges in schema public revoke all on tables from anon, authenticated';
    execute 'alter default privileges in schema public revoke all on sequences from anon, authenticated';
    execute 'alter default privileges in schema public revoke all on functions from anon, authenticated';
  end if;
end $$;
