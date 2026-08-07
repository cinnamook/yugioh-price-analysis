# CYBERSE — cross-device sync design

*Planning doc. No code here — this is the plan to hand to Claude Code when you're
ready to build sync. Written for &lt;CYBERSE&gt; as it stands: static site (app.html /
docs), all user data in browser localStorage under key `ygo_builder_v1`.*

## The problem, precisely

Your data lives in **localStorage**, which is scoped **per-origin, per-device**.
That means three separate silos today:

- desktop `app.html` opened as a `file://` page,
- the hosted PWA at `cinnamook.github.io/...`,
- your phone's installed PWA.

Even the desktop file and the hosted site on the *same computer* don't share
storage — different origins. The only bridge right now is manual **Backup all
(.json) → import**. Sync replaces that with "your collection follows you."

Good news: the whole app state is already **one serializable object**. Sync is
about moving that object between devices, not restructuring the app.

## Recommendation: Supabase

For a personal app *that you've said should grow a forum and a marketplace*
(Looking to Sell / Trade / For), **Supabase** is the right foundation:

- **Free tier** covers this many times over (500 MB Postgres, generous auth).
- **Real auth** — email magic-link (passwordless) or Google sign-in. Trivial for
  one user now; already multi-user for the forum later.
- **Postgres + row-level security** is the correct base for the eventual
  marketplace (listings, other people's data) — you won't have to re-platform.
- Clean JS client; the public "anon" key is *designed* to ship in the browser as
  long as row-level security is on.

Honest alternative: **Firestore** is slightly less code for pure personal sync
(offline cache + realtime built in), but it's NoSQL and Google-locked, so you'd
likely rebuild it when the marketplace arrives. Given your stated direction,
Supabase avoids that rewrite. If you decide the forum is *not* happening,
Firestore is the lower-effort path.

## Data model (start tiny)

One row holds your whole state blob. Normalize later only if/when you need
server-side queries (marketplace, cross-user meta).

```
table app_state (
  user_id     uuid  references auth.users  primary key,
  data        jsonb,          -- the ygo_builder_v1 object, verbatim
  updated_at  timestamptz     -- for conflict resolution
)
-- Row-level security: a user can read/write ONLY their own row.
```

That's the entire Phase-1 schema. The app already produces `data` every time it
saves.

## How it behaves

1. **Sign in** — a "Sign in to sync" affordance; magic-link email is simplest
   (no password to handle, no password rules to trip over). Session persists.
2. **On load** (signed in): fetch the remote row. If `remote.updated_at` is newer
   than the local last-sync marker, adopt remote into localStorage and re-render;
   otherwise keep local.
3. **On change**: the existing `sv()` save hook also schedules a **debounced**
   push (~2–3 s after the last edit) of `{data, updated_at}` when online.
4. **Offline**: queue the push; flush on reconnect. The PWA already caches the
   shell, so the app keeps working; sync just resumes when there's a connection.
5. **Conflict**: **last-write-wins** by `updated_at`. For a single user who rarely
   edits two devices at once, this is fine — with one caveat below.

## The decisions that are yours to make

- **Conflict safety.** Last-write-wins can lose edits if you change device A while
  offline, *then* change device B before A ever syncs — B's save wins and A's
  edits vanish. Acceptable for v1 (rare in single-user life). If you want it
  safer, v2 options: a "remote is newer, overwrite?" prompt on push, or
  per-section merge (decks/collection/bank merged independently). Recommend:
  ship LWW, add a "last synced ✓ / syncing…" indicator so you can *see* state,
  revisit merge only if it actually bites.

- ~~**Which app is canonical across devices.**~~ **DECIDED 2026-08-07: hosted
  everywhere.** The github.io app is the everyday app on desktop and phone, both
  synced; the local `file://` build stays as the offline / local-art extra and is
  deliberately out of sync. Original reasoning below.
  OAuth redirects and CORS don't play
  nicely with `file://`, so sync realistically targets the **hosted** app on all
  devices — including desktop, opened as the github.io URL in a browser tab. The
  local `file://ap­p.html` stays as the fully-offline, local-2.3 GB-art power
  version but *out* of sync. Cleanest story: **hosted = your synced everyday app,
  everywhere; local file = offline/local-art extra.** The alternative (make
  desktop also the hosted URL and drop the local file) is simpler mentally but
  gives up instant local art. Your call.

- ~~**Auth method.**~~ **DECIDED 2026-08-07: magic-link email** — nothing to
  remember, and no password ever handled by the app. (Google sign-in remains one
  Supabase setting away if it's ever wanted.)

## Security notes (so it's done right)

- Ship the **anon** key only, with **row-level security ON**. Never embed the
  `service_role` key in the client.
- Magic-link / OAuth means the actual authentication happens in Supabase's own
  flow — the app never handles your password. (Keeps us clear of entering
  credentials into fields, which is off-limits anyway.)

## Rollout

- **Phase 1 — working sync.** Supabase project, magic-link auth, `app_state` +
  RLS, sign-in affordance, pull-on-load, debounced push, last-write-wins. Ship to
  the hosted PWA. This alone gives you real cross-device sync. Roughly a focused
  Claude Code session — no rewrite, because state is already one object.
- **Phase 2 — polish.** "Last synced" indicator + manual "Sync now", offline
  write-queue hardening, conflict safety (version check or per-section merge).
- **Phase 3 — the community layer (far horizon).** Normalize into real tables,
  public LFS/LFT/LF listings, other users. The auth + RLS you built in Phase 1 is
  already the foundation.

## Setting it up — the five things that actually went wrong

Phase 1 shipped 2026-08-07 and is verified working end to end: desktop push,
phone pull, real data. Everything below was hit for real getting there; each one
fails in a way that doesn't obviously point at its cause.

1. **A brand-new user gets the "Confirm signup" template, not "Magic Link."**
   `signInWithOtp({shouldCreateUser:true})` on an address that doesn't exist yet
   creates the user, and Supabase then sends the *signup confirmation* email.
   Putting `{{ .Token }}` in Magic Link alone produces an email with no code in
   it. **Both templates need `{{ .Token }}`** — Magic Link takes over for every
   sign-in after the account exists.

2. **The OTP length is a project setting, not a constant.** Supabase allows 6–10
   digits and 6 is only the default; this project sends 8. Don't hardcode a
   length or a `maxlength` in the client — validate a minimum and let the server
   reject a wrong code.

3. **Site URL defaults to `http://localhost:3000`.** Until it's changed
   (Authentication → URL Configuration) every `{{ .ConfirmationURL }}` in an
   email points at a dead local server. Set it to the hosted app URL. This
   matters less with codes than with links, but a dead link in your own email is
   still a bug.

4. **With "auto-expose new tables" OFF, GRANT is mandatory.** PostgREST derives
   visibility from role privileges, so without
   `grant select, insert, update on public.app_state to authenticated;` the table
   is invisible to the client — `PGRST205 "Could not find the table ... in the
   schema cache"` — no matter how correct the RLS policies are. GRANT and RLS are
   separate layers: GRANT decides whether a role may touch the table, RLS decides
   which rows. Grant to `authenticated` only, never `anon`.

   Useful signal: with the grants right, an anonymous request returns `42501
   permission denied` rather than `PGRST205`. Supabase's error text will suggest
   `GRANT ... TO anon` to fix it — **don't**, that would make the data public.

5. **`sv()` is the sync hook, so anything that bypasses `sv()` bypasses sync.**
   Hooking the single save function covers all 33 mutation sites — but `imJson()`
   (restore-from-backup) deliberately writes the whole state blob straight to
   localStorage and reloads, and so wrote straight past the hook. The failure is
   quiet and looks like a *sync* bug rather than an *import* bug: sign in on an
   empty device (which pushes that empty state up), import a backup, and the pull
   after reload sees remote isn't newer, finds nothing dirty, and never pushes.
   The device looks correct while the server still holds the empty state, and
   every other device dutifully pulls nothing. `imJson()` now calls
   `syncMarkDirty()`; the flag is in localStorage so it survives the reload.

   General rule for future work: **grep for `localStorage.setItem(KEY` and check
   every hit reaches the sync layer.** There are three — `sv()`, `imJson()`, and
   `adopt()` — and only the first goes through the obvious path.

**Migrating existing data.** `file://` and the hosted origin have separate
localStorage, so the local app's collection does not follow you. Export **Backup
all (.json)** from the local app and import it into the hosted app *before* the
first sign-in — signing in empty pushes an empty state to the server, which other
devices then pull. (Trap 5 above made this worse than it needed to be: the import
itself didn't push either. Fixed, but the ordering advice still stands.)

## Cost

Supabase free tier — far beyond a personal app's needs. $0.

## A ready prompt for Claude Code (Phase 1)

> Add cross-device sync to CYBERSE using Supabase, per SYNC_DESIGN.md. Phase 1
> only: magic-link auth, an `app_state(user_id, data jsonb, updated_at)` table with
> row-level security, a "Sign in to sync" affordance, pull-on-load, and a debounced
> push wired into the existing `sv()` save. Last-write-wins by `updated_at`. Target
> the hosted (docs/) build, keep the anon key + RLS pattern, and don't break the
> `file://` desktop path (sync simply stays off there). Show me the schema, RLS
> policy, and your plan before writing the app code.
