# &lt;CYBERSE&gt; — YGO Price Tool

**CYBERSE** is a personal Yu-Gi-Oh! price/collection app (Final Fantasy-inspired UI, opens to a game-style
main menu) built on top of the analysis in `analysis/notebook.ipynb`.
Grows over time from a local price history. Separate from the portfolio notebook on purpose —
the notebook answers a question; this is a product.

## Components

| File | What it does |
|------|--------------|
| `pipeline/collect_snapshot.py` | Pulls a dated price snapshot from YGOPRODeck into `data/ygo.db`. Run daily (see below). Stdlib only. |
| `app/screener.py` | Generates `screener.html` — filter/sort/search the whole catalog by price, rarity, ban status, archetype, age, plus a cross-marketplace "gap" flag. |
| `app/deck_planner.py` | Prices a `.ydk` decklist at current prices; computes full deck value and cost-to-complete after what you own. Writes `deck_report.html`. |
| `app/build_builder.py` | Generates `builder.html` — an **interactive** app: search cards, add to a Deck / Collection / Wishlist, pick a rarity per line, see live totals + cost-to-finish. Lists save in the browser; export/import `.json`, export deck `.ydk`. |
| `app/download_images.py` | Optional: downloads card art to `data/images/` (resumable, gentle) so the app shows images in card popups. Run `python3 app/download_images.py --limit 500` in chunks. |
| `app/build_app.py` | **THE unified app** → `app.html`. Merges the screener + builder: Browse with filters, click a card for a detail popup (text, per-rarity prices, price-history sparkline), and add to Deck / Collection / Wishlist from anywhere. Multiple named decks, search within lists, add-to-deck from collection, mark the rarity you own. Supersedes `screener.html` and `builder.html`. |

## Daily collection (do this once)

Price history **cannot be back-filled**, so the collector must run every day going forward.
Add a cron job (`crontab -e`) — use the full path to your Python (`which python3`):

```
0 18 * * * cd "$HOME/CYBERSE" && /FULL/PATH/TO/python3 pipeline/collect_snapshot.py >> data/collector.log 2>&1
```

`data/ygo.db` is gitignored and irreplaceable once history accrues — **back it up** (Time Machine / a copy).

## Using the screener

```
python3 app/screener.py  # rebuild from the newest snapshot
open screener.html       # or just double-click it
```

## Using the deck planner

Export a deck as `.ydk` from the YGOPRODeck deck builder (or EDOPro), then price it at the rarity you want:

```
python3 app/deck_planner.py mydeck.ydk                        # cheapest printing per card (budget build)
python3 app/deck_planner.py mydeck.ydk --rarity "Secret Rare" # everything at that rarity where it exists
python3 app/deck_planner.py mydeck.ydk --overrides mine.csv   # per-card rarity (CSV rows: card_id_or_name,rarity)
python3 app/deck_planner.py mydeck.ydk --own owned.ydk        # subtract cards you already own
open deck_report.html
```

A card not printed/priced in the requested rarity falls back to cheapest, flagged `‡`. Rarity names are the
canonical ones (Common, Super Rare, Ultra Rare, Secret Rare, Prismatic Secret Rare, Starlight Rare, …).
`app/sample_deck.ydk` and `pipeline/rarity_overrides.csv` are included as examples. `owned.ydk` is just a .ydk of what you own.

## Roadmap

- **Phase 0 — data foundation** ✅ collector + SQLite DB (`cards`, `price_history`, + empty `collection`/`wantlist`).
- **Phase 1 — screener** ✅ browse/filter/sort + cross-market gap flag.
- **Phase 2 — price tracker** ⏳ *needs a few weeks of history* — trends, biggest movers, "dropped X% below its own average" (the real, honest deal signal).
- **Phase 3 — deck planner** ✅ price a `.ydk` deck, cost-to-complete after owned cards.
- **Phase 4 — competitive viability + deploy** — join meta/tournament data (the biggest unmeasured price driver), then grow into a shareable web app.

## Honest note on "what's good to buy"

A structural model **cannot** find deals from a single snapshot: it explains only ~20% of price,
and everything it can't see (competitive viability, hype, condition) is exactly what makes cards
expensive. So a real buy signal needs either **price history** (Phase 2 — compare a card to its own
past) or **viability data** (Phase 4). Phase 1 is honest screening, not deal prediction.
