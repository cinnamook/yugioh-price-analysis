# Decision record — the judgment calls

Snapshot: 14,477 cards, pulled 2026-08-05. Numbers below are from `profile_data.py`
(regenerate with `python3 analysis/profile_data.py`, from the repo root).

Six scope decisions had to be settled before anything could be analysed, and every one
of them could defensibly have gone the other way. This file records what the evidence
looked like at the time, the call, and the reasoning. The same reasoning appears inline
in `notebook.ipynb`, immediately above the code that acts on it. Decision 1 is the one
that changed the shape of the whole study.

---

## 1. Unit of analysis — card vs. printing  *(decided FIRST; it changes everything)*

**Numbers:** 14,477 cards → 44,287 printings. Median 2 printings/card, max 78. 96.6% have
at least one printing.

**The tension the profiler exposes:** the two price fields live at *different levels*.
- `card_prices` (TCGplayer etc.) is **one block per card** — the market's current lowest, blind to which printing.
- `set_price` is **per printing** — rarity-specific.

So the decision isn't cosmetic: it dictates *which price you can even use*, and whether
"rarity of printing" (a headline driver in the question) is a variable at all. At the
**card** level, rarity isn't well-defined (a card has many). At the **printing** level, it
is — but the same card appears up to 78 times, so rows aren't independent.

**Options:**
- **Cards** (n≈14k): clean one-row-per-card, use `card_prices`. But you lose rarity as a driver, or must pick a "representative" printing.
- **Printings** (n≈44k): rarity becomes a real driver, use `set_price`. But heavy non-independence (same card repeated), and you're now explaining *printing* price, not *card* price.

**Call:** **Cards** — one row per card, priced at card-level TCGplayer.

**Because:** printings was the starting position, and for a good reason: rarity is a
printing-level attribute and rarity was the headline variable, so analysing printings was
the only way to let it drive anything. The profiler vetoed it. `set_price` is `$0.00` for
**72% of printings**, and that missingness is not random — it is heaviest on cards that
don't trade, and whether a card trades tracks ban status. That is the worst possible shape
for missing data here: it correlates with the treatment in the exact sub-question the study
was built to answer, so it would have biased the headline estimate rather than merely
adding noise. Dropping to cards costs the per-printing view of rarity and buys back a
price field with 96.5% coverage, rarity re-entered as a card attribute (the highest rarity
a card was printed in), and genuine independence between rows — one card, one observation,
no clustering needed. Losing a variable to measurement quality is a smaller loss than
keeping it and biasing the finding it was supposed to support.

---

## 2. Price source

**Numbers:** Coverage: 96.5% of cards have TCGplayer > 0.
The five sources disagree *hard* — median dearest/cheapest ratio **12.9x**, and on **91.4%**
of cards the dearest source is >2x the cheapest. Cheapest source: Cardmarket on 9,909 cards,
TCGplayer on 3,254.

**Honest caveat to write down:** part of that gap is currency — `cardmarket_price` is in
**euros**, compared numerically against USD, so Cardmarket looks artificially "cheapest."
The disagreement is real but not purely a data-quality signal.

**Call:** **Card-level TCGplayer.**

**Because:** it is the largest US marketplace, it has the best coverage of the five
(96.5%), and it matches the TCG ban-list format chosen in #6 — pairing an OCG ban status
with a US price would be comparing two different markets. The alternative, blending the
sources, is worse than it looks: they disagree by a median 12.9x, and part of that spread
is a EUR-vs-USD artifact from Cardmarket, so an average across them would silently mix
currencies as well as markets and produce a number belonging to no real marketplace. With
disagreement that large, picking one source and naming it is more honest than a blend that
hides both problems. The cost is that these are **asks, not transactions** — a listing
nobody has met — which matters most for thin-market cards, disproportionately the rare and
banned ones this study cares about. That limitation is stated rather than solved.

---

## 3. What does 0.00 / missing mean?

**Numbers (TCGplayer):** 0 truly missing/blank, but **510 cards (3.5%) are exactly $0.00**.
Since blanks show up as `0.00`, a zero almost certainly means *"no active TCGplayer listing / no data,"* not "free."

**Options:** treat 0.00 as **missing → drop** (cleanest; you analyze 13,967 priced cards) vs.
keep as a real zero (distorts every average and the log-transform can't take log(0)).

**Call:** **Treat as missing and drop** — 510 cards, leaving 13,967 priced.

**Because:** the API returns blanks as `0.00`, so the zeros are an encoding artifact, not
observations. A Starlight Rare at `$0.00` is unlisted, not free. Keeping them as real zeros
would drag every mean toward the floor and pile artificial mass at the bottom of a
distribution whose shape is the whole point of decision #4 — and `log(0)` is undefined, so
the transform chosen there could not run at all. Dropping 3.5% of rows is the cheaper of
the two errors by a wide margin. Worth being explicit that this drop is not perfectly
clean either: a card with no active listing is a card with little demand, so the excluded
set is not a random 3.5%. It is a limitation, not a free lunch — but it removes cards at
the quiet end of the market rather than in the banned/rare group the analysis turns on.

---

## 4. Skew handling

**Numbers (TCGplayer > 0):** mean **$1.21** vs. median **$0.19** (6.4x apart). p90 $0.99,
p99 $12.39, max $1,800. The top 1% of cards hold **59%** of all dollar value.

This isn't mild skew — it's the shape of the whole dataset. Means describe a handful of
chase cards; the typical card is a ~$0.19 bulk common.

**Options:** **log-transform** price (keeps all cards, linear models behave, interpret in
% terms) vs. **medians / rank methods** (robust, no transform, but limits which models you
can run). Either is defensible; what the brief asks for is a stated choice and a reason.

**Call:** **Log-transform** — model `log(price)`.

**Because:** this is not skew to be corrected, it is the actual shape of the market: a few
hundred chase cards and a long tail of bulk commons, with the top 1% holding 59% of all
dollar value. Modelled in levels, OLS would spend nearly all of its fit on those few
hundred cards and the resulting coefficients would describe the chase market rather than
the catalogue. In logs, no small group dominates, and every coefficient reads as an
approximate percentage change — which is how price actually gets discussed ("a step up the
rarity ladder is worth about +32%"). Medians and rank methods were the real alternative and
are perfectly defensible; they were passed over because they constrain which models can be
run and give up the percentage interpretation that makes the results legible.

---

## 5. Reprints — flag or exclude?

**Numbers:** **67.7%** of cards have been reprinted (>1 printing); **11.9%** have appeared
in a Structure Deck (the cheap-regardless case the brief names).

**The catch:** reprints aren't a fringe to drop — they're **two-thirds of the data**.
Excluding all reprinted cards leaves ~4,700 cards and badly skews toward newer/scarcer ones
(worsens the survivorship problem).

**Options:** **flag** (add a `reprinted` / `in_structure_deck` indicator, keep everyone, let
it be a variable) vs. **exclude** (cleaner "playability signal" but throws away 68% and adds bias).

**Call:** **Flag, don't exclude** — keep every card, add reprint features.

**Because:** at 67.7%, reprints are not a contaminating fringe that can be trimmed; they
are the dataset. Excluding them would discard two-thirds of the data and leave a remainder
skewed toward newer and scarcer cards, making the survivorship problem worse rather than
better — buying a cleaner "playability signal" at the price of a sample that no longer
represents the catalogue. The stronger reason is what exclusion would have cost: reprinting
turned out to be one of the largest effects in the model, around **−36%**. Filtering those
cards out would have removed a headline finding from the study and left no trace that it
had ever been there. A silent filter destroys evidence; a flag turns the same judgment into
a measured, reportable result.

---

## 6. Ban-list format & the absence question

**Numbers:** only **315 cards (2.2%)** carry a `banlist_info` block; the other **97.8% have
no block at all** — which is *information* (legal/unlimited), not a missing value to fill.
Within the block, **TCG** status: Forbidden 117, Limited 94, Semi-Limited 10 — and 94 blocks
have *no* `ban_tcg` key (they're OCG/GOAT-only restricted, i.e. unlimited in TCG).

**Implication for the sub-question:** under **TCG format**, the "restricted" group is
~221 cards vs. ~14,256 unlimited. Small treatment group, but enough to test "does ban status
predict price?" — just underpowered for fine slicing.

**Call:** **TCG format**, and **absence encoded as Unlimited**, re-levelled as the baseline.

**Because:** TCG is the largest and best-documented of the three lists, and it matches the
TCGplayer price source from #2 — a card's OCG status has no bearing on what it sells for in
a US market. The absence question is the more consequential half. The 97.8% of cards with no
`banlist_info` block are not missing data waiting to be imputed or dropped; the block is
absent *because the card is legal*, which makes those 14,256 cards the control group. Read
as missing and dropped, the comparison group disappears entirely and there is nothing left
to measure a ban premium against. Encoding absence as Unlimited and re-levelling it as the
baseline is what makes every ban coefficient read as "versus an otherwise-comparable legal
card." The treatment group is small at ~221 cards — enough to answer the yes/no question,
too small to slice finely, which is why no finer cut is attempted.

---

## 7. Rarity is a scarcity confound (context, not a separate decision)

Median `set_price` climbs with rarity regardless of the card: Common **$1.44** → Rare $2.82
→ Super $2.97 → Ultra $3.03 → Secret **$4.57**. So rarity partly measures *print run*, not
*playability* — the confound to name whenever rarity shows up as "explaining" price.

Decision #1 moved rarity from a per-printing variable to a card attribute (the highest
rarity a card was printed in), but that does not dissolve the confound — it carries it over
intact. When the model reports that a step up the rarity ladder is worth about +32%, that
figure is measuring scarcity at least as much as desirability, and it is why the study's
honest summary is "scarcity, not playability" rather than a claim about card quality.

---

## Where these decisions land

Each call above is implemented in `notebook.ipynb`'s data-cleaning section, with this
reasoning as the markdown directly above the code that acts on it. Decisions #1 and #6
between them set the ceiling on what the ban-status result can claim, and both are revisited
in the notebook's Limitations section — which is the part of the analysis that matters most.
