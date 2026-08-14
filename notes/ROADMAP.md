# CYBERSE — roadmap & game plan

*The single in-repo source of the plan, so Claude Code (and any future session)
sees the whole trajectory. Companion to CLAUDE.md (how it's built) and
SYNC_DESIGN.md (the detailed spec for the next milestone). Last updated
2026-08-07.*

## North star

A personal Yu-Gi-Oh! **pocket app** that grows into a small **platform**: your
collection/decks/budget/playtesting on your phone, and eventually **online duels**,
a **mini marketplace**, and **shareable profiles & collections**. Everything below
ladders up to that. The order is chosen so each step lays foundation for the next —
auth + sync + hosting are the base the whole platform stands on.

## Status — done

- **Core app** (`app/build_app.py` → `app.html` / `docs/`): browse, decks
  (main/extra/side), collection, wishlist, bank/budget, playtest odds, match log,
  sets browser, meta, analytics. Vanilla JS + localStorage.
- **Multi-rarity / conditions** per collection & wishlist line.
- **Solo playtest board** — DuelingBook-style manual field (5 monster / 5 S-T / 2
  EMZ / field spell, interactable deck/extra/GY/banished piles, tap-to-move,
  ATK/DEF/Set). No rules automation yet.
- **Mobile**: installable PWA (manifest + service worker, versioned cache),
  hosted on **GitHub Pages** from `docs/`, card art via CDN when hosted. Full
  responsive layout pass. Live at
  `https://cinnamook.github.io/yugioh-price-analysis/`.

- **Cross-device sync — Phase 1 shipped 2026-08-07.** Supabase: emailed one-time
  code (not a clickable link — see SYNC_DESIGN.md), one
  `app_state(user_id, data jsonb, updated_at)` row with row-level security and a
  DB-owned `updated_at`, pull-on-load, debounced push wired into `sv()`,
  last-write-wins with a keep-mine / use-synced prompt (plus auto-backup) whenever
  a pull would otherwise discard unsynced local edits. Schema in
  `pipeline/sync_schema.sql`; setup steps and traps in SYNC_DESIGN.md. This is also the
  **auth foundation** the marketplace / profiles / online duels will reuse.

  **Decided 2026-08-07:** the **hosted** app is the everyday app on *every*
  device, desktop included — the only viable sync target, since auth redirects
  don't work from `file://`. The local `file://` build stays as the offline /
  local-art extra, deliberately **out of sync**.

- **The daily job publishes, and fails loudly — shipped 2026-08-13.** Price history
  can't be back-filled, so the collector is the one irreplaceable thing here — and it
  used to fail silently into a log nobody reads. `pipeline/check_freshness.py` now
  reports the newest snapshot, counts permanent holes in the history, and exits
  non-zero when stale; `scripts/refresh.command` runs it, raises a **macOS
  notification** on any failure, and then **publishes automatically**, so the phone
  gets fresh prices daily instead of whenever a publish was remembered. Two
  deliberate guards: a day that failed its freshness check is never published, and
  an unattended publish is skipped when `app/build_app.py` has uncommitted changes,
  since publish commits the generator with `docs/` and would otherwise push work in
  progress to a public repo. The app also computes its own staleness at runtime
  (`snapAge()`) and ambers the Home snapshot chip past 3 days — the macOS
  notification never reaches the phone, and the phone is where it gets noticed.

## Next up

Nothing large is committed yet. The nearest candidates, roughly by effort:

- **Sync Phase 2** — the "last synced" indicator and manual *Sync now* are
  **done (2026-08-09)**: both already existed, but `lastSync` was held only in
  memory, so after a reload the chip said "Synced ✓" with no time and Profile's
  LAST SYNCED figure disappeared entirely — exactly when you most want to know
  whether the phone is current. It is now persisted (`ygo_sync_at`), stamped on
  push, on a no-op pull and on adopting a remote copy, cleared on sign-out, and
  the chip refreshes itself in place every 30s instead of freezing at whatever
  it read when the menu was last drawn. Still open: offline write-queue
  hardening, and conflict safety beyond last-write-wins if it ever actually bites.
- ~~**Mobile numeric keypads**~~ — **audited 2026-08-09 and already complete.** All 19
  numeric fields carry `inputmode`, `decimal` vs `numeric` is assigned correctly
  (money vs integers), quantities are +/− steppers rather than typed, and the only
  `prompt()` calls ask for deck names. Nothing left to do here.
- ~~**Duel-field work**~~ — a large pass shipped 2026-08-07 (drag, life points,
  Xyz materials, tokens, declared effects, an opponent's side, pile menus, turn
  phases, card info, mobile ergonomics). **Now parked** until the multiplayer
  work, per SIM_BOARD_PLAN.md; remaining Tier 1/2 items wait unless something
  specific gets in the way while playing.

## Backlog

### QoL / mobile polish
- ~~**First-run experience**~~ — **done 2026-08-09.** Two real defects, both found by
  opening the app at phone width with localStorage cleared: the quick-start card told
  new users to "begin in **Cards & decks**", a Home group the narrow layout doesn't
  render at all (Browse/Decks/Collection live in the bottom bar there), and the Deck
  tab — where the quick-start sends them — showed three sections each saying just
  "empty". The intro now names what is actually on screen at that width, and each deck
  section says what belongs in it and points at an action on the same screen.
- ~~**Numeric inputs open the number pad on mobile**~~ — **done** (verified by audit
  2026-08-09; see "Next up" above).
- ~~**Phone-width polish pass**~~ — **done 2026-08-09.** Audited all 12 views at 390px
  with real data. Horizontal overflow was **zero everywhere** — the earlier responsive
  pass holds. Three controls were genuinely too small to hit and are now fixed behind
  the existing 900px breakpoint, so desktop is untouched (re-measured to confirm):
  the row-delete ✕ 18×20 → 38×37, the per-row rarity/condition selects 20 → 35 tall,
  and the sync dot — which navigates to Profile — 9×9 → a 44×44 hit area via a
  transparent pseudo-element. ✕ and the selects land at ~37 rather than the 44 ideal
  on purpose: getting to 44 costs ~10px on every row and makes long lists worse.
  The solo board was deliberately left alone — its geometry is driven by `--bside`
  and a blanket min-height would fight it.
- **Text inputs still fight you on mobile** — no input anywhere sets
  `autocapitalize` / `autocorrect` / `spellcheck`, so iOS capitalizes and
  autocorrects inside the six search-style fields (card name, archetype, list
  filter, add-a-card, sets search, and the match log's `+Ash, -Maxx` impact field).
  Same class of problem as the keypads, and the natural successor to it.
- ~~**Import a deck from a link**~~ — **shipped 2026-08-09.** "Import from link" in the
  deck bar accepts a **ydke://** URI (the EDOPro / DuelingBook / YGOPRODeck
  interchange format, which carries the whole deck inside the URI, so it needs no
  network), a ydke:// embedded in a longer share link, or an http(s) link to a
  `.ydk` file, which it fetches and parses.
  **Known limit, not a bug:** a YGOPRODeck *deck page* URL cannot be imported —
  that page sends no `Access-Control-Allow-Origin`, so the browser blocks any
  cross-origin read of it. Verified 2026-08-09. The failure message says so and
  points at the deck page's own **YDKE** button instead.

### Duel-field improvements (extend the solo board)
- **Life-point calculator / tracker** — per-player LP with +/− adjustments and a
  small history; the natural companion to the manual board.
- **Xyz overlay / materials** — attach monsters *under* an Xyz monster as
  materials, with a visual overlay and a detach action. (The board slots already
  hold stacks, so the data side is close; this is mostly the attach/detach UX.)
- **Tap-and-drag** movement as an alternative/addition to tap-to-move.
- Likely adjacent later: counters/tokens, coin/die, a phase indicator.

### Pocket niceties
- ~~**Shareable deck links**~~ — **shipped 2026-08-09.** "Copy deck link" puts the
  whole deck in the URL fragment as a `ydke://` URI, so sharing needs no server, no
  account and no row anywhere; the recipient's app decodes it locally. A full
  60/15/15 deck is ~500 characters of payload, far inside any URL limit. A fragment
  is never sent to a server, which is where someone else's deck list belongs.
  Opening a link never mutates anything silently: it asks first, adds the deck as a
  **new** deck, consumes the fragment so a reload can't re-prompt, and a corrupt
  fragment is ignored. Links made from the `file://` build point at the hosted app,
  since a local path is useless to anyone else.
- ~~**Shareable collection**~~ — **shipped 2026-08-09.** Too big for a URL, so it
  stores a snapshot in a new `shares` table — the project's first public read path.
  Kept off `app_state` deliberately, snapshot rather than live view, and an
  allow-list of card/rarity/condition/quantity that excludes the per-line price
  override and everything from bank/match log. Public reads go through a
  `security definer` `get_share(slug)` function rather than a table grant, so the
  table cannot be listed. "Stop sharing" deletes the row. Design notes in
  SYNC_DESIGN.md.
  **Live as of 2026-08-13** — `pipeline/sync_schema.sql` has been run against the
  Supabase project. Verified from outside with the public anon key: `get_share()` on
  an unknown slug returns `[]` rather than an error, and `anon` gets `42501
  insufficient_privilege` on both `shares` and `app_state` — so a slug can be
  redeemed but the table cannot be listed, which is the property the
  security-definer design exists to guarantee.
- Still open: a trade log, deck-journal notes, a locals calendar. **No camera scan.**

### Data / price accuracy
- Manual price overrides (done). Next: prototype the free **JustTCG** API for real
  per-printing prices on tracked cards, reducing manual entry.

## Far horizon — the platform layer

These are the north-star features. They all depend on the auth + sync + hosting
base, which is why sync comes first.

- **Online duels** — real-time multiplayer on top of the solo board (networking +
  backend + game-state sync; the biggest single build).
- **Mini marketplace** — **Looking to Sell / Trade / For** (LFS/LFT/LF) listings.
- **Shareable profiles & collections** — public read-only views of a user's
  collection/decks/record.
- A broader **community / forum** around all of the above.

## How we work

Pair-programming; **Ryan makes the calls** and values understanding how things are
built. Day-to-day coding is in **Claude Code** (runs in this repo). Planning,
roadmap, and design docs are maintained on the Cowork side and land here as files
like this one. Don't let two tools edit the working tree at once.
