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
- ~~**Numeric inputs open the number pad on mobile**~~ — **done** (verified by audit
  2026-08-09; see "Next up" above).
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
- Shareable deck / collection links, a trade log, deck-journal notes, a locals
  calendar. **No camera scan.**

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
