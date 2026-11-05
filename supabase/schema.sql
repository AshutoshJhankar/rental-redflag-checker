-- Rental Agreement Red-Flag Checker: run once in Supabase -> SQL Editor.
create table if not exists public.analyses (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  expires_at  timestamptz not null,
  file_name   text not null,
  risk_score  int  not null,
  risk_level  text not null,
  result      jsonb not null          -- key terms + flags (already PII-masked). The PDF is never stored.
);
create index if not exists analyses_expires_at_idx on public.analyses (expires_at);

-- Row Level Security ON with no policies: the public/anon key can't read or write anything.
-- Only the backend, using the secret (service_role) key, can access the table.
alter table public.analyses enable row level security;
grant select, insert, update, delete on public.analyses to service_role;

-- Optional nightly cleanup of expired rows (Database -> Extensions -> enable pg_cron first):
-- select cron.schedule('purge-expired-analyses', '0 3 * * *', $$delete from public.analyses where expires_at < now()$$);
