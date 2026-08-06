#!/usr/bin/env python3
"""
Phase 3 — deck planner. Prices a .ydk decklist at current TCGplayer prices and computes
cost-to-complete (subtracting what you already own). Writes deck_report.html + prints a summary.

  python3 deck_planner.py mydeck.ydk                 # full cost of the deck
  python3 deck_planner.py mydeck.ydk --own owned.ydk # subtract cards you own (a .ydk of your collection)

.ydk files are the standard export from the YGOPRODeck deck builder / EDOPro (one card passcode per
line, under #main / #extra / !side). Stdlib only.
"""
import sqlite3, os, sys, argparse, json
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "data", "ygo.db")

def parse_ydk(path):
    """Return {card_id: count} across main+extra+side."""
    counts = Counter()
    for line in open(path):
        line = line.strip()
        if line.isdigit():
            counts[int(line)] += 1
    return counts

def latest_prices():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    date = con.execute("SELECT MAX(snapshot_date) FROM price_history").fetchone()[0]
    rows = con.execute("""SELECT c.card_id, c.name, c.card_class, c.top_rarity_tier, c.ban_tcg,
                                 p.tcgplayer AS price
                          FROM cards c JOIN price_history p USING(card_id)
                          WHERE p.snapshot_date=?""", [date]).fetchall()
    con.close()
    return date, {r["card_id"]: dict(r) for r in rows}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck"); ap.add_argument("--own")
    a = ap.parse_args()
    need  = parse_ydk(a.deck)
    owned = parse_ydk(a.own) if a.own else {}
    date, cat = latest_prices()

    lines, total, complete, missing = [], 0.0, 0.0, []
    for cid, qty in need.items():
        info = cat.get(cid)
        if not info or info["price"] is None:
            missing.append(cid); continue
        have   = owned.get(cid, 0)
        to_buy = max(0, qty - have)
        price  = info["price"]
        total    += qty * price
        complete += to_buy * price
        lines.append(dict(name=info["name"], cl=info["card_class"], rr=info["top_rarity_tier"],
                          bn=info["ban_tcg"], qty=qty, have=have, buy=to_buy, price=price,
                          line=to_buy*price, value=qty*price))
    lines.sort(key=lambda x: -x["line"])

    print(f"\nDeck: {os.path.basename(a.deck)}  |  snapshot {date}")
    print(f"cards: {sum(need.values())} ({len(need)} unique)  |  full deck value: ${total:,.2f}"
          f"  |  cost to complete: ${complete:,.2f}")
    if missing: print(f"  ({len(missing)} card ids not found / unpriced: {missing[:6]}{'…' if len(missing)>6 else ''})")
    print("\n  most expensive to acquire:")
    for l in [x for x in lines if x["buy"] > 0][:10]:
        print(f"    {l['buy']}x {l['name'][:34]:<34} @ ${l['price']:>7.2f} = ${l['line']:>8.2f}")

    trs = "".join(
        f"<tr><td class='r'>{l['qty']}</td><td class='r mut'>{l['have']}</td><td class='r'>{l['buy']}</td>"
        f"<td class='nm'>{esc(l['name'])}</td><td>{l['cl']}</td><td class='r'>{l['rr']}</td>"
        f"<td>{'' if l['bn']=='Unlimited' else l['bn']}</td>"
        f"<td class='r'>${l['price']:.2f}</td><td class='r {'pos' if l['buy'] else 'mut'}'>${l['line']:.2f}</td></tr>"
        for l in lines)
    html = HTML.replace("__DECK__", esc(os.path.basename(a.deck))).replace("__DATE__", date)\
        .replace("__NC__", str(sum(need.values()))).replace("__NU__", str(len(need)))\
        .replace("__TOT__", f"{total:,.2f}").replace("__COMP__", f"{complete:,.2f}").replace("__ROWS__", trs)
    out = os.path.join(HERE, "deck_report.html"); open(out, "w").write(html)
    print(f"\nwrote {out}")

def esc(s): return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

HTML = r"""<!doctype html><meta charset=utf-8><title>Deck — __DECK__</title><style>
:root{--bg:#0f1020;--card:#1a1b2e;--ink:#e8e8f0;--mut:#9a9ab0;--line:#2a2b45;--pos:#5fd08a}
body{font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
header{padding:16px 22px;border-bottom:1px solid var(--line)}h1{margin:0;font-size:18px}
.cards{display:flex;gap:22px;padding:14px 22px;flex-wrap:wrap}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 18px;min-width:150px}
.kpi .v{font-size:22px;font-weight:700}.kpi .l{color:var(--mut);font-size:12px}
.kpi.hl .v{color:var(--pos)}
table{border-collapse:collapse;width:calc(100% - 44px);margin:6px 22px 40px}
th,td{padding:5px 9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mut);font-weight:600}.r{text-align:right;font-variant-numeric:tabular-nums}
.nm{font-weight:600}.mut{color:var(--mut)}.pos{color:var(--pos)}
</style>
<header><h1>Deck Planner — __DECK__</h1><div class=mut style="color:#9a9ab0;font-size:12px">snapshot __DATE__ · TCGplayer prices</div></header>
<div class=cards>
<div class=kpi><div class=v>__NC__</div><div class=l>cards (__NU__ unique)</div></div>
<div class=kpi><div class=v>$__TOT__</div><div class=l>full deck value</div></div>
<div class="kpi hl"><div class=v>$__COMP__</div><div class=l>cost to complete (after owned)</div></div>
</div>
<table><thead><tr><th class=r>Need</th><th class=r>Own</th><th class=r>Buy</th><th>Card</th><th>Class</th>
<th class=r>Rar</th><th>Ban</th><th class=r>Unit $</th><th class=r>To-buy $</th></tr></thead>
<tbody>__ROWS__</tbody></table>"""

if __name__ == "__main__":
    main()
