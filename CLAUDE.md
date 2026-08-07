# CLAUDE.md — &lt;CYBERSE&gt; project brief

Personal Yu-Gi-Oh! hub for Ryan Nguyen (UCSD Data Science). One app that holds his
collection, decks, budget, playtesting, match records, sets, and meta. Final
Fantasy / Xenoblade-inspired UI. Long-term goal: a mobile "pocket app."

## How it's built (important — read before editing)

Static-site generation, no framework, no server:

- **`collect_snapshot.py`** pulls a daily price/printing snapshot from the
  YGOPRODeck API into a SQLite DB **`data/ygo.db`** (gitignored; back it up —
  price history can't be re-pulled).
- **`build_app.py`** reads `data/ygo.db` and writes **`app.html`** — a single
  self-contained page (vanilla JS + localStorage, all card data embedded as JSON).
- **All the app's JavaScript lives INSIDE `build_app.py`** as a big Python raw
  string (`HTML = r"""..."""`). Edit `build_app.py`, never `app.html` directly —
  `app.html` is generated and gitignored.
- User data (collection, decks, logs) lives in the **browser's localStorage**
  (key `ygo_builder_v1`), never in the HTML. A rebuild never touches it.

## Commands

```bash
# rebuild the app after editing build_app.py (run from the project folder)
python3 build_app.py

# open the desktop version
open app.html

# refresh data + rebuild (what the daily 1pm launchd job runs)
bash refresh.command

# rebuild + push the hosted phone version (GitHub Pages)
bash publish.command
```

## Mobile / hosting

- `build_app.py` also emits a **`docs/`** bundle for **GitHub Pages**:
  `docs/index.html` (same page), `manifest.json`, `sw.js` (service worker,
  versioned by build date), and `icons/`. Repo: `cinnamook/yugioh-price-analysis`,
  Pages served from `main` `/docs`. Live URL:
  `https://cinnamook.github.io/yugioh-price-analysis/`.
- **Card art is protocol-aware** (see `imgSrc()` / `IMGBASE` in `build_app.py`):
  on `file://` (desktop) it uses the local `data/images/` cache (~2.3 GB,
  gitignored); when hosted it uses the YGOPRODeck CDN, so the hosted app stays
  ~13 MB. Never commit `data/images/`.
- The app is **installable and works offline** (data/prices/decks/playtest);
  only card images need a connection when hosted.

## Current plan — see ROADMAP.md

The responsive mobile pass is **done**: nav scroll strip, shrink-to-fit KPI grid,
`.tscroll` table containers, a solo board that scales via `--bside`/`--bgap`, and
iOS safe-area insets (`--sat`/`--sar`/`--sab`/`--sal`) on the header, `.wrap` and
overlays. Sticky offsets key off `--hh`, measured from the real header at runtime.

**ROADMAP.md is the single in-repo source of the plan** — north star, status,
backlog, far horizon. Read it first.

**Next milestone: cross-device sync.** Supabase magic-link auth, one
`app_state(user_id, data jsonb, updated_at)` row with row-level security,
pull-on-load plus a debounced push wired into the existing `sv()`, last-write-wins.
Full spec in **SYNC_DESIGN.md** — read it before starting. One decision is open
first: whether the hosted app becomes the everyday app on every device, with the
`file://` build kept only as the offline / local-art extra.

Backlog items most likely to come next (full list in ROADMAP.md):

- **Mobile numeric keypads** — every field expecting a number (life points,
  quantities, prices, budget amounts, game scores) should carry the right
  `inputmode`/`type` so phones show the number pad instead of the full keyboard.
  Some fields already do; the work is making it consistent.
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

- Run `python3 build_app.py` **from the project folder** (it reads `data/ygo.db`
  via a path relative to the script).
- Test the hosted/PWA path over **http** (e.g. `python3 -m http.server`), not
  `file://` — service workers don't run from `file://`, and `IMGBASE` switches on
  protocol.
- Two commits already exist locally that need `git push`: the solo board and the
  PWA bundle.
- Data sources: YGOPRODeck free API prices only ~30% of printings. No free API
  for competitive META — meta is a manual watchlist. JustTCG (free, per-printing)
  is a possible future price upgrade.

## Working style

Pair-programming; **Ryan makes the calls**. He values understanding *how* things
are built and honesty about limitations. Explain trade-offs, propose, let him
decide. Backlog after the mobile pass: cross-device **sync** (the real pocket-app
unlock), then pocket niceties (shareable deck/collection links, trade log,
deck-journal notes — **no camera scan**), and a far-horizon community layer
(Looking to Sell / Trade / For listings).
