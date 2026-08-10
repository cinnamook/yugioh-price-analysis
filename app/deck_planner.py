#!/usr/bin/env python3
"""
Phase 3 — deck planner (rarity-aware). Prices a .ydk decklist and computes cost-to-complete.
Each card is priced at the rarity you choose:

  python3 app/deck_planner.py deck.ydk                          # cheapest printing per card (budget build)
  python3 app/deck_planner.py deck.ydk --rarity "Secret Rare"   # everything at that rarity where it exists
  python3 app/deck_planner.py deck.ydk --overrides mine.csv      # per-card rarity (CSV: card_id_or_name,rarity)
  python3 app/deck_planner.py deck.ydk --own owned.ydk           # subtract cards you already own

A card that isn't printed/priced in the requested rarity falls back to cheapest (flagged ‡).
Writes deck_report.html. Stdlib only.
"""
import sqlite3, os, argparse, csv
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))   # app/
ROOT = os.path.dirname(HERE)                        # repo root — data/ and the generated pages live there
DB   = os.path.join(ROOT, "data", "ygo.db")

def parse_ydk(path):
    c = Counter()
    for line in open(path):
        line = line.strip()
        if line.isdigit(): c[int(line)] += 1
    return c

def load_catalog():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    date = con.execute("SELECT MAX(snapshot_date) FROM price_history").fetchone()[0]
    cat = {}
    for r in con.execute("""SELECT c.card_id, c.name, c.card_class, c.ban_tcg, p.tcgplayer
                            FROM cards c JOIN price_history p USING(card_id) WHERE p.snapshot_date=?""", [date]):
        cat[r["card_id"]] = {"name": r["name"], "cl": r["card_class"], "bn": r["ban_tcg"],
                             "tcg": r["tcgplayer"], "rar": {}}
    for r in con.execute("SELECT card_id, rarity, price FROM card_rarities").fetchall():
        if r["card_id"] in cat: cat[r["card_id"]]["rar"][r["rarity"]] = r["price"]
    con.close()
    name2id = {v["name"].lower(): k for k, v in cat.items()}
    return date, cat, name2id

def cheapest(info):
    if info["tcg"] is not None: return "cheapest", info["tcg"]
    priced = [(p, r) for r, p in info["rar"].items() if p is not None]
    if priced: p, r = min(priced); return r, p
    return None, None

def price_card(info, want, ov):
    target = ov or want
    if target:
        p = info["rar"].get(target)
        if p is not None: return target, p, False
        r, p = cheapest(info); return r, p, True          # requested rarity missing/unpriced -> fallback
    r, p = cheapest(info); return r, p, False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck"); ap.add_argument("--own"); ap.add_argument("--rarity"); ap.add_argument("--overrides")
    a = ap.parse_args()
    need  = parse_ydk(a.deck)
    owned = parse_ydk(a.own) if a.own else {}
    date, cat, name2id = load_catalog()

    ov = {}
    if a.overrides:
        for row in csv.reader(open(a.overrides)):
            if len(row) < 2 or not row[0].strip(): continue
            key, rar = row[0].strip(), row[1].strip()
            cid = int(key) if key.isdigit() else name2id.get(key.lower())
            if cid: ov[cid] = rar

    lines, total, complete, missing, fallbacks = [], 0.0, 0.0, [], 0
    for cid, qty in need.items():
        info = cat.get(cid)
        if not info: missing.append(cid); continue
        rar, price, fb = price_card(info, a.rarity, ov.get(cid))
        if price is None: missing.append(cid); continue
        if fb: fallbacks += 1
        have, tobuy = owned.get(cid, 0), max(0, qty - owned.get(cid, 0))
        total += qty*price; complete += tobuy*price
        lines.append(dict(name=info["name"], cl=info["cl"], bn=info["bn"], rar=rar, fb=fb,
                          qty=qty, have=have, buy=tobuy, price=price, line=tobuy*price))
    lines.sort(key=lambda x: -x["line"])
    mode = f'rarity = "{a.rarity}"' if a.rarity else ("per-card overrides" if a.overrides else "cheapest printing")

    print(f"\nDeck: {os.path.basename(a.deck)} | snapshot {date} | mode: {mode}")
    print(f"cards: {sum(need.values())} ({len(need)} unique) | full value: ${total:,.2f} | to complete: ${complete:,.2f}")
    if fallbacks: print(f"  ‡ {fallbacks} card(s) not available in the requested rarity — priced at cheapest instead")
    if missing:  print(f"  {len(missing)} unpriced/unknown id(s): {missing[:6]}{'…' if len(missing)>6 else ''}")
    print("\n  most expensive to acquire:")
    for l in [x for x in lines if x["buy"] > 0][:10]:
        print(f"    {l['buy']}x {l['name'][:32]:<32} {l['rar']:<20} @ ${l['price']:>8.2f} = ${l['line']:>8.2f}")

    trs = "".join(
        f"<tr><td class='r'>{l['qty']}</td><td class='r mut'>{l['have']}</td><td class='r'>{l['buy']}</td>"
        f"<td class='nm'>{esc(l['name'])}</td><td>{l['cl']}</td>"
        f"<td>{esc(l['rar'])}{'<span class=fb> ‡</span>' if l['fb'] else ''}</td>"
        f"<td>{'' if l['bn']=='Unlimited' else l['bn']}</td>"
        f"<td class='r'>${l['price']:.2f}</td><td class='r {'pos' if l['buy'] else 'mut'}'>${l['line']:.2f}</td></tr>"
        for l in lines)
    html = (HTML.replace("__DECK__", esc(os.path.basename(a.deck))).replace("__DATE__", date).replace("__MODE__", esc(mode))
            .replace("__NC__", str(sum(need.values()))).replace("__NU__", str(len(need)))
            .replace("__TOT__", f"{total:,.2f}").replace("__COMP__", f"{complete:,.2f}").replace("__ROWS__", trs))
    out = os.path.join(ROOT, "deck_report.html"); open(out, "w").write(html)
    print(f"\nwrote {out}")

def esc(s): return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

HTML = r"""<!doctype html><meta charset=utf-8><title>Deck — __DECK__</title><style>
:root{--bg:#0f1020;--card:#1a1b2e;--ink:#e8e8f0;--mut:#9a9ab0;--line:#2a2b45;--pos:#5fd08a;--fb:#e8b45f}
body{font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
header{padding:16px 22px;border-bottom:1px solid var(--line)}h1{margin:0;font-size:18px}
.sub{color:var(--mut);font-size:12px}
.cards{display:flex;gap:22px;padding:14px 22px;flex-wrap:wrap}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 18px;min-width:150px}
.kpi .v{font-size:22px;font-weight:700}.kpi .l{color:var(--mut);font-size:12px}.kpi.hl .v{color:var(--pos)}
table{border-collapse:collapse;width:calc(100% - 44px);margin:6px 22px 40px}
th,td{padding:5px 9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mut);font-weight:600}.r{text-align:right;font-variant-numeric:tabular-nums}
.nm{font-weight:600}.mut{color:var(--mut)}.pos{color:var(--pos)}.fb{color:var(--fb)}
</style>
<header><h1>Deck Planner — __DECK__</h1><div class=sub>snapshot __DATE__ · TCGplayer prices · pricing mode: <b>__MODE__</b> · ‡ = fell back to cheapest</div></header>
<div class=cards>
<div class=kpi><div class=v>__NC__</div><div class=l>cards (__NU__ unique)</div></div>
<div class=kpi><div class=v>$__TOT__</div><div class=l>full deck value</div></div>
<div class="kpi hl"><div class=v>$__COMP__</div><div class=l>cost to complete (after owned)</div></div>
</div>
<table><thead><tr><th class=r>Need</th><th class=r>Own</th><th class=r>Buy</th><th>Card</th><th>Class</th>
<th>Rarity</th><th>Ban</th><th class=r>Unit $</th><th class=r>To-buy $</th></tr></thead>
<tbody>__ROWS__</tbody></table>"""

if __name__ == "__main__":
    main()
