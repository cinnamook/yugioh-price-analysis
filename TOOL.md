# YGO Price Tool

A personal Yu-Gi-Oh! price/collection tool built on top of the analysis in `notebook.ipynb`.
Grows over time from a local price history. Separate from the portfolio notebook on purpose —
the notebook answers a question; this is a product.

## Components

| File | What it does |
|------|--------------|
| `collect_snapshot.py` | Pulls a dated price snapshot from YGOPRODeck into `data/ygo.db`. Run daily (see below). Stdlib only. |
| `screener.py` | Generates `screener.html` — filter/sort/search the whole catalog by price, rarity, ban status, archetype, age, plus a cross-marketplace "gap" flag. |
| `deck_planner.py` | Prices a `.ydk` decklist at current prices; computes full deck value and cost-to-complete after what you own. Writes `deck_report.html`. |

## Daily collection (do this once)

Price history **cannot be back-filled**, so the collector must run every day going forward.
Add a cron job (`crontab -e`) — use the full path to your Python (`which python3`):

```
0 18 * * * cd "$HOME/Downloads/TCG Market Analysis" && /FULL/PATH/TO/python3 collect_snapshot.py >> data/collector.log 2>&1
```

`data/ygo.db` is gitignored and irreplaceable once history accrues — **back it up** (Time Machine / a copy).

## Using the screener

```
python3 screener.py      # rebuild from the newest snapshot
open screener.html       # or just double-click it
```

## Using the deck planner

Export a deck as `.ydk` from the YGOPRODeck deck builder (or EDOPro), then:

```
python3 deck_planner.py mydeck.ydk                 # full cost of the deck
python3 deck_planner.py mydeck.ydk --own owned.ydk # subtract cards you already own
open deck_report.html
```

`owned.ydk` is just a .ydk listing the cards you own (a running "collection" export). `sample_deck.ydk`
is included as an example to try.

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
