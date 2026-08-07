-- <CYBERSE> cross-device sync — Phase 1 schema
-- Run this once in the Supabase SQL editor (Dashboard → SQL Editor → New query → Run).
-- Spec: SYNC_DESIGN.md.

-- ---------------------------------------------------------------------------
-- One row per user holding the whole app-state blob (the ygo_builder_v1 object).
-- Normalising into real tables is Phase 3, when the marketplace needs to query
-- across users; until then a single jsonb column is the right shape.
-- ---------------------------------------------------------------------------
create table if not exists public.app_state (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  data       jsonb       not null,
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- The DATABASE owns updated_at. The client never sends it and cannot forge it,
-- so sync ordering can't be corrupted by a device with a wrong clock — which
-- matters because updated_at is the conflict-resolution key.
-- ---------------------------------------------------------------------------
create or replace function public.app_state_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists app_state_set_updated_at on public.app_state;
create trigger app_state_set_updated_at
  before update on public.app_state
  for each row execute function public.app_state_touch_updated_at();

-- INSERTs get it from the column default above; UPDATEs from the trigger.

-- ---------------------------------------------------------------------------
-- Row-level security: a user can only ever touch their own row.
-- This is what makes shipping the public anon key in the browser safe.
-- ---------------------------------------------------------------------------
alter table public.app_state enable row level security;

drop policy if exists "read own row"   on public.app_state;
drop policy if exists "insert own row" on public.app_state;
drop policy if exists "update own row" on public.app_state;

create policy "read own row"
  on public.app_state for select
  using (auth.uid() = user_id);

-- both insert AND update are required: the client upserts
create policy "insert own row"
  on public.app_state for insert
  with check (auth.uid() = user_id);

create policy "update own row"
  on public.app_state for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- Deliberately NO delete policy — a browser bug can't wipe the synced copy.

-- ---------------------------------------------------------------------------
-- Verify (optional): should list rls enabled + the three policies.
-- ---------------------------------------------------------------------------
-- select relrowsecurity from pg_class where relname = 'app_state';
-- select policyname, cmd from pg_policies where tablename = 'app_state';
