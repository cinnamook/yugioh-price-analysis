# CLAUDE.md — &lt;CYBERSE&gt; project brief

Personal Yu-Gi-Oh! hub for Ryan Nguyen (UCSD Data Science). One app that holds his
collection, decks, budget, playtesting, match records, sets, and meta. Final
Fantasy / Xenoblade-inspired UI. Long-term goal: a mobile "pocket app."

## Repo layout

```
analysis/   the original question: notebook.ipynb, DECISIONS.md, profile_data.py, figures/
pipeline/   collect_snapshot.py (daily pull), banlist/rarity overrides, sync_schema.sql, the launchd plist
app/        build_app.py + the older generators, vendor/ (pinned supabase-js)
notes/      ROADMAP.md, JOURNEY.md, SYNC_DESIGN.md, SIM_BOARD_PLAN.md, TOOL.md
scripts/    refresh / publish / setup_automation .command wrappers
data/       the SQLite DB, cached pulls, image cache (mostly gitignored)
docs/       GENERATED GitHub Pages bundle — output, not documentation. Never hand-edit.
```

All scripts resolve paths from their own location, so they can be run from
anywhere; the generated pages (`app.html` and friends) are still written to the
repo **root**, because on `file://` the page resolves card art relative to
itself (`IMGBASE = 'data/images/'`) and so must sit beside `data/`.

## How it's built (important — read before editing)

Static-site generation, no framework, no server:

- **`pipeline/collect_snapshot.py`** pulls a daily price/printing snapshot from the
  YGOPRODeck API into a SQLite DB **`data/ygo.db`** (gitignored; back it up —
  price history can't be re-pulled).
- **`app/build_app.py`** reads `data/ygo.db` and writes **`app.html`** — a single
  self-contained page (vanilla JS + localStorage, all card data embedded as JSON).
- **All the app's JavaScript lives INSIDE `app/build_app.py`** as a big Python raw
  string (`HTML = r"""..."""`). Edit `app/build_app.py`, never `app.html` directly —
  `app.html` is generated and gitignored.
- User data (collection, decks, logs) lives in the **browser's localStorage**
  (key `ygo_builder_v1`), never in the HTML. A rebuild never touches it.

## Commands

```bash
# rebuild the app after editing app/build_app.py
python3 app/build_app.py

# open the desktop version
open app.html

# refresh data + rebuild (what the daily 1pm launchd job runs)
bash scripts/refresh.command

# rebuild + push the hosted phone version (GitHub Pages)
bash scripts/publish.command
```

## Mobile / hosting

- `app/build_app.py` also emits a **`docs/`** bundle for **GitHub Pages**:
  `docs/index.html` (same page), `manifest.json`, `sw.js` (service worker,
  versioned by build date), and `icons/`. Repo: `cinnamook/yugioh-price-analysis`,
  Pages served from `main` `/docs`. Live URL:
  `https://cinnamook.github.io/yugioh-price-analysis/`.
- **Card art is protocol-aware** (see `imgSrc()` / `IMGBASE` in `app/build_app.py`):
  on `file://` (desktop) it uses the local `data/images/` cache (~2.3 GB,
  gitignored); when hosted it uses the YGOPRODeck CDN, so the hosted app stays
  ~13 MB. Never commit `data/images/`.
- The app is **installable and works offline** (data/prices/decks/playtest);
  only card images need a connection when hosted.

## Current plan — see notes/ROADMAP.md

The responsive mobile pass is **done**: nav scroll strip, shrink-to-fit KPI grid,
`.tscroll` table containers, a solo board that scales via `--bside`/`--bgap`, and
iOS safe-area insets (`--sat`/`--sar`/`--sab`/`--sal`) on the header, `.wrap` and
overlays. Sticky offsets key off `--hh`, measured from the real header at runtime.

**notes/ROADMAP.md is the single in-repo source of the plan** — north star, status,
backlog, far horizon. Read it first.

**Cross-device sync (Phase 1) shipped 2026-08-07.** Supabase, configured in
`app/build_app.py` (`SUPABASE_URL` / `SUPABASE_ANON_KEY` — the publishable key is
public by design; never put a secret key there). Schema in `pipeline/sync_schema.sql`.
The client lives in one block near the end of the template:

- Auth is an **emailed one-time code**, not a clickable link — on iOS a link
  authenticates Safari, whose storage is separate from the installed PWA. The
  code length is a Supabase project setting (6–10), so don't hardcode it.
- `sv()` is the only hook: debounced ~2.5s push, flushed on
  `visibilitychange`/`pagehide` because iOS kills backgrounded PWAs mid-debounce.
- `updated_at` is owned by a DB trigger and read back via `.select()`; it's the
  conflict key, so the client never sends it.
- A **dirty flag** guards conflicts. If a pull finds remote newer *and* local is
  dirty, the app writes a backup to disk and asks keep-mine vs use-synced rather
  than adopting silently. Steady state is last-write-wins.
- Sync is off on `file://` and when the build has no Supabase config; in both
  cases the app behaves exactly as before.

**notes/SYNC_DESIGN.md has a "Setting it up" section** listing the four traps that cost
real time (signup vs magic-link template, OTP length, Site URL, GRANT with
auto-expose off). Read it before touching auth config.

Backlog items most likely to come next (full list in notes/ROADMAP.md):

- **Mobile text-input attributes** — no input in the template sets
  `autocapitalize`/`autocorrect`/`spellcheck`, so iOS capitalizes and autocorrects
  inside the search fields. (The *numeric* keypad pass is done — audited
  2026-08-09, all 19 numeric fields carry the right `inputmode`.)
- **Duel-field improvements** (extend the solo board) — a **life-point tracker**
  with +/− adjustments and a short history; an **Xyz materials overlay** (attach
  monsters under an Xyz monster, with detach; slots already hold stacks, so this
  is mostly attach/detach UX); and **tap-and-drag** movement alongside the
  existing tap-to-move.

## Data model notes

- **Multi-rarity (done):** `collection`/`wishlist` entries are arrays of lines
  `[{rar, cond, q, ov}]` (own multiple rarities/conditions per card). Decks stay
  single-line per card. Helpers: `ownQ(id)`, `isMulti(list)`, `lref(list,id,li)`,
  line-index (`li`) threaded through setters. Migration runs in `load()`.
- **Decks** split `main` / `extra` / `side`; Extra-deck cards (Fusion/Synchro/
  Xyz/Link) auto-route via each card's embedded `ex` flag.
- **Solo board (done):** DuelingBook-like — discrete zones (`mon`×5, `st`×5,
  `emz`×2, `fs`×1 as slot arrays) + piles (`deck`/`ex`/`hand`/`gy`/`ban`);
  tap-to-move with ATK/DEF/Set modes; clickable pile viewers.

## Gotchas

- The generators find `data/ygo.db` relative to their own file, so `python3
  app/build_app.py` works from any directory — but it always writes `app.html`
  and `docs/` at the repo root.
- Test the hosted/PWA path over **http** (e.g. `python3 -m http.server`), not
  `file://` — service workers don't run from `file://`, and `IMGBASE` switches on
  protocol.
- When testing over http, **unregister the service worker first**. Its fetch
  handler answers navigations from cache and ignores the query string, so a
  `?cachebust=` on the URL will *not* get you the fresh page — you'll silently
  test the previous build. `scripts/publish.command` stages `app/build_app.py`
  alongside `docs/`, so the generator and its output can't drift apart.
- Data sources: YGOPRODeck free API prices only ~30% of printings. No free API
  for competitive META — meta is a manual watchlist. JustTCG (free, per-printing)
  is a possible future price upgrade.

## Working style

Pair-programming; **Ryan makes the calls**. He values understanding *how* things
are built and honesty about limitations. Explain trade-offs, propose, let him
decide. The backlog and the long-term trajectory live in **notes/ROADMAP.md** — keep
them there rather than duplicating them here, so the two can't drift.
