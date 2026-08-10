"""
Profiles the cached YGOPRODeck snapshot to produce the numbers behind each judgment
call in the brief. This is NOT the analysis — it exists so Ryan can make each scope
decision against real data. Reads data/cardinfo_raw.json, prints a report, and writes
decision_numbers.json.

Run:  python3 analysis/profile_data.py
"""
import json, os, statistics, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))   # analysis/
ROOT = os.path.dirname(HERE)                        # repo root — data/ lives there
RAW = os.path.join(ROOT, "data", "cardinfo_raw.json")

PRICE_KEYS = ["tcgplayer_price", "cardmarket_price", "ebay_price",
              "amazon_price", "coolstuffinc_price"]

def load():
    if not os.path.exists(RAW):
        sys.exit(f"Missing {RAW} — pull the data first (see README).")
    with open(RAW) as f:
        return json.load(f)["data"]

def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def pct(n, d):
    return f"{100*n/d:5.1f}%" if d else "  n/a"

def main():
    cards = load()
    N = len(cards)
    out = {"n_cards": N}
    print(f"\n{'='*70}\nYGOPRODeck snapshot profile — {N} cards\n{'='*70}")

    # ---- 1. Card vs printing -------------------------------------------------
    printings = sum(len(c.get("card_sets", []) or []) for c in cards)
    n_with_sets = sum(1 for c in cards if c.get("card_sets"))
    per_card = [len(c.get("card_sets", []) or []) for c in cards]
    per_card_nz = [p for p in per_card if p > 0]
    print("\n[1] UNIT OF ANALYSIS — card vs printing")
    print(f"    cards ................... {N}")
    print(f"    total printings ........ {printings}")
    print(f"    cards with >=1 printing  {n_with_sets} ({pct(n_with_sets,N)})")
    if per_card_nz:
        print(f"    printings per card ..... median {statistics.median(per_card_nz):.0f}, "
              f"max {max(per_card_nz)}, mean {statistics.mean(per_card_nz):.1f}")
    out["printings_total"] = printings
    out["cards_with_sets"] = n_with_sets

    # ---- 2. Prices present / zeros / missing --------------------------------
    has_prices = 0
    tcg_missing = tcg_zero = tcg_valid = 0
    for c in cards:
        cp = (c.get("card_prices") or [{}])[0] if isinstance(c.get("card_prices"), list) else (c.get("card_prices") or {})
        if cp:
            has_prices += 1
        v = fnum(cp.get("tcgplayer_price"))
        if v is None:
            tcg_missing += 1
        elif v == 0:
            tcg_zero += 1
        else:
            tcg_valid += 1
    print("\n[2] PRICE COVERAGE (TCGplayer as example)")
    print(f"    cards with a card_prices block  {has_prices} ({pct(has_prices,N)})")
    print(f"    tcgplayer > 0 .................. {tcg_valid} ({pct(tcg_valid,N)})")
    print(f"    tcgplayer == 0 ................ {tcg_zero} ({pct(tcg_zero,N)})  <- decide what 0.00 means")
    print(f"    tcgplayer missing/blank ....... {tcg_missing} ({pct(tcg_missing,N)})")
    out["tcg_valid"] = tcg_valid; out["tcg_zero"] = tcg_zero; out["tcg_missing"] = tcg_missing

    # ---- 3. How often do the 5 price sources disagree? ----------------------
    # For cards where >=2 sources are > 0, look at spread (max/min ratio) and
    # whether the "cheapest source" ranking is stable.
    ratios = []
    big_gap = 0            # max/min > 2x
    cheapest = Counter()
    n_multi = 0
    for c in cards:
        cp = (c.get("card_prices") or [{}])[0] if isinstance(c.get("card_prices"), list) else (c.get("card_prices") or {})
        vals = {k: fnum(cp.get(k)) for k in PRICE_KEYS}
        pos = {k: v for k, v in vals.items() if v and v > 0}
        if len(pos) >= 2:
            n_multi += 1
            hi, lo = max(pos.values()), min(pos.values())
            ratios.append(hi / lo)
            if hi / lo > 2:
                big_gap += 1
            cheapest[min(pos, key=pos.get)] += 1
    print("\n[3] DO THE 5 PRICE SOURCES AGREE?  (cards with >=2 positive sources)")
    print(f"    comparable cards ............... {n_multi}")
    if ratios:
        ratios.sort()
        med = ratios[len(ratios)//2]
        print(f"    max/min price ratio ........... median {med:.2f}x, "
              f"90th pctile {ratios[int(0.9*len(ratios))]:.2f}x, max {max(ratios):.1f}x")
        print(f"    cards where dearest > 2x cheapest  {big_gap} ({pct(big_gap,n_multi)})")
        print(f"    which source is cheapest (count): "
              + ", ".join(f"{k.split('_')[0]}={v}" for k, v in cheapest.most_common()))
    out["price_disagreement_median_ratio"] = ratios[len(ratios)//2] if ratios else None
    out["price_big_gap_share"] = (big_gap / n_multi) if n_multi else None

    # ---- 4. Skew of price -----------------------------------------------------
    tcg = sorted(v for c in cards
                 for v in [fnum(((c.get("card_prices") or [{}])[0] if isinstance(c.get("card_prices"), list) else (c.get("card_prices") or {})).get("tcgplayer_price"))]
                 if v and v > 0)
    print("\n[4] PRICE SKEW (TCGplayer > 0)")
    if tcg:
        n = len(tcg)
        q = lambda p: tcg[min(n-1, int(p*n))]
        mean = sum(tcg)/n
        print(f"    n={n}  mean ${mean:.2f}  median ${q(0.5):.2f}")
        print(f"    p50 ${q(0.5):.2f}  p90 ${q(0.9):.2f}  p99 ${q(0.99):.2f}  max ${tcg[-1]:.2f}")
        top1_share = sum(tcg[int(0.99*n):]) / sum(tcg)
        print(f"    mean/median ratio {mean/q(0.5):.1f}x   <- right-tail; top 1% hold "
              f"{100*top1_share:.0f}% of all dollar value")
    out["price_mean"] = mean if tcg else None
    out["price_median"] = q(0.5) if tcg else None

    # ---- 5. Reprints ----------------------------------------------------------
    reprinted = sum(1 for c in cards if len(c.get("card_sets", []) or []) > 1)
    in_structure = sum(1 for c in cards
                       if any("structure deck" in (s.get("set_name","").lower())
                              for s in (c.get("card_sets") or [])))
    print("\n[5] REPRINTS")
    print(f"    cards with >1 printing (reprinted)  {reprinted} ({pct(reprinted,N)})")
    print(f"    cards ever in a Structure Deck ...  {in_structure} ({pct(in_structure,N)})")
    out["reprinted"] = reprinted; out["in_structure_deck"] = in_structure

    # ---- 6. Ban-list presence -------------------------------------------------
    has_ban = 0
    tcg_status = Counter()
    for c in cards:
        bi = c.get("banlist_info")
        if bi:
            has_ban += 1
            tcg_status[bi.get("ban_tcg", "—")] += 1
    print("\n[6] BAN-LIST — absence is information")
    print(f"    cards WITH a banlist_info block  {has_ban} ({pct(has_ban,N)})")
    print(f"    cards with NO banlist_info ......  {N-has_ban} ({pct(N-has_ban,N)})  <- not a gap")
    print(f"    ban_tcg values: " + ", ".join(f"{k}={v}" for k, v in tcg_status.most_common()))
    out["has_banlist_info"] = has_ban

    # ---- 7. Rarity as a scarcity confound ------------------------------------
    # Median set_price by rarity, to show a Secret Rare can outprice by print run.
    from collections import defaultdict
    by_rarity = defaultdict(list)
    for c in cards:
        for s in (c.get("card_sets") or []):
            v = fnum(s.get("set_price"))
            if v and v > 0:
                by_rarity[s.get("set_rarity","?")].append(v)
    print("\n[7] RARITY AS A SCARCITY CONFOUND (median set_price by rarity, top by volume)")
    rows = sorted(by_rarity.items(), key=lambda kv: -len(kv[1]))[:8]
    for r, vals in rows:
        vals.sort()
        print(f"    {r:<22} n={len(vals):<6} median ${vals[len(vals)//2]:.2f}")

    with open(os.path.join(HERE, "decision_numbers.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n{'='*70}\nWrote decision_numbers.json\n{'='*70}\n")

if __name__ == "__main__":
    main()
