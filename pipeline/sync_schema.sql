-- <CYBERSE> cross-device sync — Phase 1 schema
-- Run this once in the Supabase SQL editor (Dashboard → SQL Editor → New query → Run).
-- Spec: notes/SYNC_DESIGN.md.

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
-- Table privileges. These are a SEPARATE layer from RLS and both are required:
--   GRANT = may this role touch the table at all
--   RLS   = which rows it may touch
-- This project has "auto-expose new tables" OFF, so nothing is granted
-- automatically and PostgREST decides visibility from these privileges — without
-- them the client can't see app_state at all ("Could not find the table ... in
-- the schema cache"), no matter how the policies are written.
--
-- Granted to `authenticated` only, never `anon`: the app reads and writes solely
-- when signed in. The verb list matches the policies exactly — no DELETE.
-- ---------------------------------------------------------------------------
grant usage on schema public to authenticated;   -- normally already true; harmless to repeat
grant select, insert, update on public.app_state to authenticated;

-- No sequence grants needed: the primary key is a uuid from auth.users, not a serial.

-- ---------------------------------------------------------------------------
-- Verify (optional): rls enabled, three policies, and the three privileges.
-- ---------------------------------------------------------------------------
-- select relrowsecurity from pg_class where relname = 'app_state';
-- select policyname, cmd from pg_policies where tablename = 'app_state';
-- select grantee, privilege_type from information_schema.role_table_grants
--   where table_name = 'app_state' order by grantee, privilege_type;


-- ===========================================================================
--  shares — public read-only snapshots (shareable collection)
--  Spec: notes/SYNC_DESIGN.md. Added 2026-08-09.
--
--  This is the project's FIRST public read path, so it is a separate table on
--  purpose. app_state holds everything — decks, budget, match log — and is
--  readable only by its owner. If "public" were a column on app_state instead,
--  one policy mistake would leak all of it. A separate table means a mistake can
--  only ever expose what was deliberately copied into `data`.
--
--  `data` is a SNAPSHOT taken at share time, not a live view of app_state, so it
--  cannot silently widen later. The client writes card id, rarity, condition and
--  quantity only — never the per-line price override (`ov`, "your price"), and
--  never anything from bank/budget.
-- ===========================================================================
create table if not exists public.shares (
  slug       text primary key,                 -- 96 random bits, from the client
  user_id    uuid not null references auth.users(id) on delete cascade,
  kind       text not null check (kind in ('collection')),
  data       jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists shares_user_idx on public.shares(user_id);

alter table public.shares enable row level security;

-- Owner-only policies. There is deliberately NO "select using (true)" policy:
-- see the note on get_share() below for why public reads do not go through RLS.
create policy "shares: owner reads own"   on public.shares for select
  using (auth.uid() = user_id);
create policy "shares: owner inserts own" on public.shares for insert
  with check (auth.uid() = user_id);
create policy "shares: owner updates own" on public.shares for update
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "shares: owner deletes own" on public.shares for delete
  using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
--  Public reads go through this function, NOT through a table grant.
--
--  The obvious approach — `for select using (true)` plus `grant select to anon` —
--  is wrong: it lets anyone run `select * from shares` with no filter and walk
--  every shared collection in the project. A slug is meant to be unguessable,
--  which is worthless if the whole table can be listed.
--
--  A security-definer function can only be called WITH a slug, so there is no
--  way to enumerate. anon never gets any privilege on the table itself.
-- ---------------------------------------------------------------------------
create or replace function public.get_share(p_slug text)
returns table (kind text, data jsonb, created_at timestamptz)
language sql
security definer
stable
set search_path = public
as $$ select s.kind, s.data, s.created_at from public.shares s where s.slug = p_slug $$;

revoke all on public.shares from anon;
grant select, insert, update, delete on public.shares to authenticated;
grant execute on function public.get_share(text) to anon, authenticated;

-- Verify (optional):
--   select policyname, cmd from pg_policies where tablename = 'shares';
--   select grantee, privilege_type from information_schema.role_table_grants
--     where table_name = 'shares' order by grantee;   -- anon must NOT appear
--   select * from public.get_share('nope');           -- returns 0 rows, no error
