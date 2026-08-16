# CYBERSE — cross-device sync design

*The design for the sync and sharing layer, written for CYBERSE as it stands: a
static site (`app.html` / `docs/`) with all user data in browser localStorage under
the key `ygo_builder_v1`.*

## The problem, precisely

The data lives in **localStorage**, which is scoped **per-origin, per-device**.
That means three separate silos:

- desktop `app.html` opened as a `file://` page,
- the hosted PWA at `cinnamook.github.io/...`,
- the phone's installed PWA.

Even the desktop file and the hosted site on the *same computer* don't share
storage — different origins. The only bridge before sync was a manual **Backup all
(.json) → import**. Sync replaces that with "the collection follows you."

Good news: the whole app state is already **one serializable object**. Sync is
about moving that object between devices, not restructuring the app.

## Why Supabase

For a personal app that should eventually grow a forum and a marketplace
(Looking to Sell / Trade / For), **Supabase** is the right foundation:

- **Free tier** covers this many times over (500 MB Postgres, generous auth).
- **Real auth** — email magic-link (passwordless) or Google sign-in. Trivial for
  one user now; already multi-user for the forum later.
- **Postgres + row-level security** is the correct base for the eventual
  marketplace (listings, other people's data) — no re-platforming required.
- Clean JS client; the public "anon" key is *designed* to ship in the browser as
  long as row-level security is on.

Honest alternative: **Firestore** is slightly less code for pure personal sync
(offline cache + realtime built in), but it's NoSQL and Google-locked, so it would
likely need rebuilding when the marketplace arrives. Given the stated direction,
Supabase avoids that rewrite. If the forum were definitively not happening,
Firestore would be the lower-effort path.

## Data model (start tiny)

One row holds the whole state blob. Normalize later only if and when server-side
queries are needed (marketplace, cross-user meta).

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

1. **Sign in** — a "Sign in to sync" affordance; an emailed code is simplest
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

## The decisions behind it

- **Conflict safety.** Last-write-wins can lose edits if device A changes while
  offline and *then* device B changes before A ever syncs — B's save wins and A's
  edits vanish. Acceptable for v1 (rare in single-user life). Safer v2 options: a
  "remote is newer, overwrite?" prompt on push, or per-section merge
  (decks/collection/bank merged independently). The call: ship LWW, add a
  "last synced ✓ / syncing…" indicator so the state is *visible*, and revisit merge
  only if it actually bites.

- **Which app is canonical across devices — hosted everywhere.** The github.io app
  is the everyday app on desktop and phone, both synced; the local `file://` build
  stays as the offline / local-art extra and is deliberately out of sync. OAuth
  redirects and CORS don't play nicely with `file://`, so sync realistically targets
  the **hosted** app on all devices — including desktop, opened as the github.io URL
  in a browser tab. The alternative (make desktop also the hosted URL and drop the
  local file) is simpler mentally but gives up instant local art.

- **Auth method — emailed one-time code.** Nothing to remember, and no password
  ever handled by the app. (Google sign-in remains one Supabase setting away if it's
  ever wanted.)

## Security notes (so it's done right)

- Ship the **anon** key only, with **row-level security ON**. Never embed the
  `service_role` key in the client.
- An emailed code / OAuth means the actual authentication happens in Supabase's own
  flow — the app never handles a password.

## Rollout

- **Phase 1 — working sync.** Supabase project, emailed-code auth, `app_state` +
  RLS, sign-in affordance, pull-on-load, debounced push, last-write-wins. Ship to
  the hosted PWA. This alone gives real cross-device sync, and needs no rewrite,
  because state is already one object.
- **Phase 2 — polish.** "Last synced" indicator + manual "Sync now", offline
  write-queue hardening, conflict safety (version check or per-section merge).
- **Phase 3 — the community layer (far horizon).** Normalize into real tables,
  public LFS/LFT/LF listings, other users. The auth + RLS from Phase 1 is
  already the foundation.

## Setting it up — the five things that actually went wrong

Phase 1 is verified working end to end: desktop push, phone pull, real data.
Everything below was hit for real getting there; each one fails in a way that
doesn't obviously point at its cause.

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

---

## Shareable collection

A deck fits in a URL; a collection does not (thousands of lines), so this is the
first feature that needs a **stored** snapshot — and therefore the project's
first **public read path**. Schema in `pipeline/sync_schema.sql`.

**Separate table, not a flag on `app_state`.** `app_state` holds everything —
decks, budget, match log — behind an owner-only policy. A "public" column on it
would mean one policy mistake leaks all of it. `shares` can only ever expose what
was deliberately copied into `data`.

**A snapshot, not a live view.** `data` is written at share time, so what the link
shows can never silently widen as the app grows new fields.

**What is excluded, on purpose.** The client writes card id, rarity, condition and
quantity only. Not `ov` — the per-line "your price" override — and nothing from
bank/budget or the match log. What you paid sits one field away from what you are
sharing, so the snapshot builder is an allow-list, never a delete-list.

**Reads do not go through a table grant.** The obvious `for select using (true)`
plus `grant select to anon` is wrong: it lets anyone run `select * from shares`
with no filter and walk every shared collection in the project, which makes an
unguessable slug worthless. Public reads go through `get_share(p_slug)`, a
`security definer` function that can only be called *with* a slug. `anon` holds
no privilege on the table itself.

**Revocation is real.** "Stop sharing" deletes the row, so the link dies
immediately; it does not merely hide it. The slug lives in `St.settings`, so it
rides the existing sync and can be revoked from any signed-in device.

**Slug.** 96 bits from `crypto.getRandomValues`. Unguessable but not secret —
anyone holding the link can read it. Nothing lists shares anywhere, by design.
