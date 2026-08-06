# Project journey — from a brief to a tool

A plain-English record of how this project was built and *why* each decision was made.
Two things live in this repo now: **(1)** a finished analysis notebook that answers one question,
and **(2)** a growing personal price tool built on the same data. Here's the whole path.

---

## Where we started

An empty folder and a one-page brief: *"What explains the price of a Yu-Gi-Oh! card?"* — a
cross-sectional (single-snapshot) analysis, meant as a portfolio piece to show independent
judgment on a dataset. Working style: **pair — I lay out the evidence and trade-offs, you make
each call.** That's why every decision below is *yours*, with the reasoning written down.

---

## Part 1 — The analysis notebook

1. **Confirmed the data source.** Checked the YGOPRODeck API docs and a live card to verify the
   fields existed (prices, printings, ban status, dates) before trusting them.
2. **Pulled the data — from *your* machine.** The cloud sandbox is network-locked and can't reach
   the API, so you ran the pull in your own Terminal: **14,477 cards**.
3. **Profiled before deciding.** Rather than guess, we computed the numbers behind each judgment
   call so you'd decide against evidence.
4. **Made six documented decisions** (this *is* the analysis — a reviewer reads for how you decide):

   | Decision | Call | Why |
   |----------|------|-----|
   | Unit of analysis | **Cards** (not printings) | We *started* with printings so rarity could be a driver — then found `set_price` was missing for **72%** of printings, and that missingness correlates with ban status, which would bias the headline finding. Reversed to cards. |
   | Price source | **Card-level TCGplayer** | Five marketplaces disagree ~13×; pick one, justify it, note they're asks not sales. |
   | `$0.00` prices | **Treat as missing, drop** (510 cards) | Blanks come back as 0; a Starlight Rare isn't free. `log(0)` is undefined anyway. |
   | Skew | **Log-transform price** | Mean \$1.21 vs median \$0.19; top 1% hold 59% of value. |
   | Reprints | **Flag, don't exclude** | 68% are reprinted — excluding guts the data and worsens survivorship. Make it a measured feature instead. |
   | Ban format | **TCG; absence = Unlimited** | The 97.8% with no ban record are the *control group*, not missing data. |

   Plus: explanatory model with a short predictive coda; excluded `views`/`upvotes` (endogenous —
   caused by price); dropped announced-but-unreleased cards.
5. **Engineered features & built 4 charts**, each making one point (skew, ban status, rarity, reprints).
6. **Ran the model** (OLS, robust standard errors). Headline: banned cards carry a **premium**
   (Forbidden ≈ +109%), *not* a discount — but correlation only, and the arrow likely runs backward
   (cards get banned *because* they're powerful/iconic, which is what drives demand). Rarity dominates;
   reprinting knocks ~36% off; older cards cost more.
7. **Wrote the Limitations section** — 9 specific points. This is the part that matters most.
8. **Pushed to GitHub:** `github.com/cinnamook/yugioh-price-analysis`.

---

## Part 2 — The pivot to a tool

9. **Your insight:** competitive viability is probably a huge price driver — and we'd been unable to
   measure it. That led to the **two-markets framing**: YGO prices are a *player* market (driven by
   viability, which our data can't see) stacked on a *collector* market (driven by scarcity, which it
   measures well). The model explains the collector side; the ~79% it misses is mostly the player side.
10. **You chose to go bigger:** a fleshed-out personal tool (value-finder + price tracker + deck
    planner), starting personal and growing to a portfolio web app later. Framed as **two separate
    projects** so the clean notebook stays clean.
11. **Phase 0 — data foundation:** a daily collector writing dated snapshots into a SQLite database
    (`data/ygo.db`), seeded with day one. (Hit and fixed a classic macOS Python SSL-certificate error.)
    Automated with a daily cron job — because **price history can't be back-filled**, starting the
    collection early is the single most valuable thing.
12. **Phase 1 — the honest lesson:** I built a model-based "value finder," tested it, and it **couldn't
    find deals** — a structural model can't tell "underpriced" from "low unmeasured demand" (it confirmed
    your two-markets point). So instead of shipping something that quietly doesn't work, we reframed Phase
    1 as an honest **screener** (filter/sort the catalog + a cross-marketplace gap flag) and deferred real
    deal-detection to Phase 2 (compare a card to its *own* price history) and Phase 4 (viability data).
13. **Phase 3 — deck planner:** price any decklist at current prices and compute cost-to-complete.

---

## Where we are & what's next

- ✅ **Notebook** — done, pushed, defensible.
- ✅ **Phase 0** — daily collector + database, automated.
- ✅ **Phase 1** — screener.
- ✅ **Phase 3** — deck planner.
- ⏳ **Phase 2** — price tracker: unlocks itself as the collector banks a few weeks of history.
- 🔜 **Phase 4** — competitive-viability data + deploy as a shareable web app (the portfolio finale).

## The one-line lessons (interview gold)
- *Let the data change your design.* The printings→cards reversal is the strongest thing in the notebook.
- *Absence is information.* No ban record = legal, i.e. the control group.
- *Know what your model can't see.* Low R² isn't failure — it's honesty about the player market.
- *Don't ship something that doesn't work.* Killing the fake deal-finder was the right call.
