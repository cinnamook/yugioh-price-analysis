# Decision worksheet — the judgment calls

Snapshot: 14,477 cards, pulled 2026-08-05. Numbers below are from `profile_data.py`
(regenerate anytime with `python3 profile_data.py`). Each call is **yours** — I've laid
out the evidence and the trade-offs, not the answer. Fill in "Your call" + "Because"; that
text is what goes inline in the notebook next to the decision.

---

## 1. Unit of analysis — card vs. printing  *(decide this FIRST; it changes everything)*

**Numbers:** 14,477 cards → 44,287 printings. Median 2 printings/card, max 78. 96.6% have
at least one printing.

**The tension the profiler exposes:** the two price fields live at *different levels*.
- `card_prices` (TCGplayer etc.) is **one block per card** — the market's current lowest, blind to which printing.
- `set_price` is **per printing** — rarity-specific.

So the decision isn't cosmetic: it dictates *which price you can even use*, and whether
"rarity of printing" (a headline driver in your question) is a variable at all. At the
**card** level, rarity isn't well-defined (a card has many). At the **printing** level, it
is — but the same card appears up to 78 times, so rows aren't independent.

**Options:**
- **Cards** (n≈14k): clean one-row-per-card, use `card_prices`. But you lose rarity as a driver, or must pick a "representative" printing.
- **Printings** (n≈44k): rarity becomes a real driver, use `set_price`. But heavy non-independence (same card repeated), and you're now explaining *printing* price, not *card* price.

**Your call:** _______   **Because:** _______

---

## 2. Price source

**Numbers:** you're leaning **TCGplayer**. Coverage: 96.5% of cards have TCGplayer > 0.
The five sources disagree *hard* — median dearest/cheapest ratio **12.9x**, and on **91.4%**
of cards the dearest source is >2x the cheapest. Cheapest source: Cardmarket on 9,909 cards,
TCGplayer on 3,254.

**Honest caveat to write down:** part of that gap is currency — `cardmarket_price` is in
**euros**, compared numerically against USD, so Cardmarket looks artificially "cheapest."
The disagreement is real but not purely a data-quality signal.

**Your call:** TCGplayer (leaning)   **Because:** _______ *(largest US TCG marketplace; single consistent currency; and the 12.9x cross-source spread means picking one and saying why beats blending)*

---

## 3. What does 0.00 / missing mean?

**Numbers (TCGplayer):** 0 truly missing/blank, but **510 cards (3.5%) are exactly $0.00**.
Since blanks show up as `0.00`, a zero almost certainly means *"no active TCGplayer listing / no data,"* not "free."

**Options:** treat 0.00 as **missing → drop** (cleanest; you analyze 13,967 priced cards) vs.
keep as a real zero (distorts every average and the log-transform can't take log(0)).

**Your call:** _______   **Because:** _______

---

## 4. Skew handling

**Numbers (TCGplayer > 0):** mean **$1.21** vs. median **$0.19** (6.4x apart). p90 $0.99,
p99 $12.39, max $1,800. The top 1% of cards hold **59%** of all dollar value.

This isn't mild skew — it's the shape of the whole dataset. Means describe a handful of
chase cards; the typical card is a ~$0.19 bulk common.

**Options:** **log-transform** price (keeps all cards, linear models behave, interpret in
% terms) vs. **medians / rank methods** (robust, no transform, but limits which models you
can run). Either is defensible; the brief just wants you to say which and why.

**Your call:** _______   **Because:** _______

---

## 5. Reprints — flag or exclude?

**Numbers:** **67.7%** of cards have been reprinted (>1 printing); **11.9%** have appeared
in a Structure Deck (the cheap-regardless case your brief names).

**The catch:** reprints aren't a fringe to drop — they're **two-thirds of the data**.
Excluding all reprinted cards leaves ~4,700 cards and badly skews toward newer/scarcer ones
(worsens the survivorship problem).

**Options:** **flag** (add a `reprinted` / `in_structure_deck` indicator, keep everyone, let
it be a variable) vs. **exclude** (cleaner "playability signal" but throws away 68% and adds bias).

**Your call:** _______   **Because:** _______

---

## 6. Ban-list format & the absence question

**Numbers:** only **315 cards (2.2%)** carry a `banlist_info` block; the other **97.8% have
no block at all** — which is *information* (legal/unlimited), not a missing value to fill.
Within the block, **TCG** status: Forbidden 117, Limited 94, Semi-Limited 10 — and 94 blocks
have *no* `ban_tcg` key (they're OCG/GOAT-only restricted, i.e. unlimited in TCG).

**Implication for the sub-question:** if you pick **TCG format**, your "restricted" group is
~221 cards vs. ~14,256 unlimited. Small treatment group, but enough to test "does ban status
predict price?" — just underpowered for fine slicing.

**Options:** format = **TCG** (biggest, best-documented) vs. OCG vs. GOAT. And confirm you'll
encode absence as "Unlimited," not drop it.

**Your call:** _______   **Because:** _______

---

## 7. Rarity is a scarcity confound (context, not a separate decision)

Median `set_price` climbs with rarity regardless of the card: Common **$1.44** → Rare $2.82
→ Super $2.97 → Ultra $3.03 → Secret **$4.57**. So rarity partly measures *print run*, not
*playability* — the confound to name whenever rarity shows up as "explaining" price. Relevant
mostly if you chose **printings** in #1.

---

## Once you've filled these in
Tell me your calls and I'll build the notebook skeleton around them — data-cleaning cell that
implements each decision with your reasoning as the markdown above it, then we move to the
3–4 charts. Nothing gets analyzed until these are set.
