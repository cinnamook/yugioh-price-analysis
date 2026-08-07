#!/usr/bin/env python3
"""
The unified YGO app. Reads data/ygo.db and writes app.html — a single self-contained page that
merges the screener and the builder: Browse cards with filters, click a card for a detail popup
(text, per-rarity prices, price-history sparkline), and add to Deck / Collection / Wishlist from
anywhere. Lists save in the browser; export/import JSON, export deck .ydk. Supersedes screener.html
and builder.html.

  python3 build_app.py     (run collect_snapshot.py once first so card_text + rarities exist)
Stdlib only.
"""
import sqlite3, os, json, datetime, statistics
from collections import defaultdict
from collect_snapshot import RARITY_ORDER

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "data", "ygo.db")
TODAY = datetime.date(2026, 8, 6)

def age_years(s):
    try: return round((TODAY - datetime.date.fromisoformat(s)).days/365.25, 1)
    except (TypeError, ValueError): return None

def main():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    if not con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='card_rarities'").fetchone():
        print("Run  python3 collect_snapshot.py  once first (adds card_text + the rarity table)."); return
    date = con.execute("SELECT MAX(snapshot_date) FROM price_history").fetchone()[0]
    rows = con.execute("""SELECT c.card_id,c.name,c.card_class,c.race,c.attribute,c.level,c.atk,c.def_,
                                 c.linkval,c.scale,c.type,c.ban_tcg,c.archetype,c.card_text,c.tcg_date,c.num_printings,
                                 p.tcgplayer,p.ebay,p.amazon,p.coolstuffinc
                          FROM price_history p JOIN cards c USING(card_id) WHERE p.snapshot_date=?""", [date]).fetchall()
    EXTRA = ("Fusion", "Synchro", "Xyz", "XYZ", "Link")
    rp = defaultdict(dict); rst = defaultdict(dict)
    # Load EVERY rarity a card is printed in (price may be null — the free feed only
    # prices ~30% of printings). Listing the rarity even without a price is what tells
    # the user which versions exist; unpriced ones fall back to market-low for valuation.
    # `sets` is the printing history (which sets that rarity appeared in).
    _hassets = "sets" in {c[1] for c in con.execute("PRAGMA table_info(card_rarities)")}
    for r in con.execute("SELECT * FROM card_rarities").fetchall():
        rp[r["card_id"]][r["rarity"]] = r["price"]
        if _hassets and r["sets"]:
            rst[r["card_id"]][r["rarity"]] = r["sets"]
    hist = defaultdict(list)
    for r in con.execute("SELECT card_id,snapshot_date,tcgplayer FROM price_history WHERE tcgplayer IS NOT NULL ORDER BY snapshot_date").fetchall():
        hist[r["card_id"]].append([r["snapshot_date"], r["tcgplayer"]])

    ORD = {n: i for i, n in enumerate(RARITY_ORDER)}
    cards, flagged = [], 0
    for r in rows:
        tcg = r["tcgplayer"]; others = [x for x in (r["ebay"], r["amazon"], r["coolstuffinc"]) if x and x > 0]
        ref = round(statistics.median(others), 2) if others else None
        gap = round(ref/tcg, 2) if (tcg and tcg > 0 and ref) else None
        deal = bool(gap and gap >= 2 and tcg and tcg >= 2)
        if deal: flagged += 1
        prc = rp.get(r["card_id"], {})
        hr = max(prc, key=lambda k: ORD.get(k, -1)) if prc else None
        cards.append({"i": r["card_id"], "n": r["name"], "cl": r["card_class"], "rc": r["race"],
            "at": r["attribute"], "lv": r["level"], "atk": r["atk"], "df": r["def_"], "bn": r["ban_tcg"],
            "ar": r["archetype"] or "", "ag": age_years(r["tcg_date"]), "np": r["num_printings"],
            "m": tcg, "oth": ref, "gap": gap, "deal": deal, "hr": hr, "tx": r["card_text"] or "",
            "ex": 1 if any(k in (r["type"] or "") for k in EXTRA) else 0,
            "lk": r["linkval"], "sc": r["scale"], "xy": 1 if any(k in (r["type"] or "") for k in ("Xyz","XYZ")) else 0,
            "rp": prc, "st": rst.get(r["card_id"], {}), "rd": r["tcg_date"], "h": hist.get(r["card_id"], [])[-90:]})

    # ----- Sets index (set -> [ [card_id, rarity_index], ... ]) for the Sets browser -----
    sets_list = []
    if con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='printings'").fetchone():
        ids_set = {c["i"] for c in cards}
        ridx = {n: i for i, n in enumerate(RARITY_ORDER)}
        setmap = {}
        for pr in con.execute("SELECT card_id,set_name,set_code,rarity FROM printings").fetchall():
            if pr["card_id"] not in ids_set: continue
            s = setmap.get(pr["set_name"])
            if s is None:
                s = {"n": pr["set_name"], "c": pr["set_code"] or "", "k": []}
                setmap[pr["set_name"]] = s
            s["k"].append([pr["card_id"], ridx.get(pr["rarity"], -1)])
        sets_list = sorted(setmap.values(), key=lambda s: -len(s["k"]))

    payload = json.dumps(cards).replace("</", "<\\/")
    html = (HTML.replace("__DATE__", date).replace("__N__", str(len(cards))).replace("__FLAG__", str(flagged))
            .replace("__RAR__", json.dumps(RARITY_ORDER)).replace("__SETS__", json.dumps(sets_list).replace("</", "<\\/")).replace("__DATA__", payload))
    out = os.path.join(HERE, "app.html"); open(out, "w").write(html)
    mb = os.path.getsize(out)/1e6
    print(f"snapshot {date} | {len(cards):,} cards | {flagged} gap flags | app.html {mb:.1f} MB")
    print(f"wrote {out} — open it (double-click, or: open app.html). Lists save in the browser.")

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>&lt;CYBERSE&gt; — __DATE__</title>
<link rel="preconnect" href="https://fonts.gstatic.com"><link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&display=swap" rel="stylesheet"><style>
:root{--bg:#070c1c;--bg2:#0b1330;--surf:#111d3f;--surf2:#182a55;--line:#2c3d70;--line2:#43598f;
  --ink:#eaf0ff;--mut:#93a0c4;--acc:#8fdcff;--acc2:#5566d8;--pos:#6ee0a0;--warn:#e8c66a;--dang:#ff6b81;
  --gold:#e8c66a;--gold2:#f3dd94;--sh:0 8px 30px rgba(2,6,20,.6)}
*{box-sizing:border-box}
body{font:13px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;margin:0;color:var(--ink);-webkit-font-smoothing:antialiased;
  background:radial-gradient(1100px 560px at 78% -12%,#161e30 0%,var(--bg) 55%) fixed,var(--bg)}
header{padding:12px 22px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap;position:sticky;top:0;background:rgba(11,15,23,.82);backdrop-filter:blur(12px);z-index:20}
h1{margin:0;font-size:16px;font-weight:700;letter-spacing:-.01em;display:flex;align-items:center;gap:8px}
h1::before{content:"◆";color:var(--acc);font-size:14px}
.nav{display:flex;gap:3px;background:var(--surf);padding:3px;border-radius:12px;border:1px solid var(--line)}
.nav .t{padding:6px 15px;border-radius:9px;cursor:pointer;font-size:13px;color:var(--mut);transition:.15s}
.nav .t:hover{color:var(--ink)} .nav .t.on{background:var(--acc2);color:#fff;font-weight:600}
.kpis{display:flex;gap:8px;margin-left:auto;flex-wrap:wrap}
.kpi{background:var(--surf);border:1px solid var(--line);border-radius:12px;padding:6px 14px;text-align:right;min-width:78px}
.kpi .v{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums}
.kpi.hl{border-color:rgba(87,208,138,.4)}.kpi.hl .v{color:var(--pos)}
.kpi .l{color:var(--mut);font-size:9px;text-transform:uppercase;letter-spacing:.06em;margin-top:1px}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:12px 22px;border-bottom:1px solid var(--line);background:var(--bg2)}
input,select,button{background:var(--surf);color:var(--ink);border:1px solid var(--line2);border-radius:9px;padding:7px 11px;font:inherit;font-size:12px;transition:.15s}
input:focus,select:focus{outline:none;border-color:var(--acc);box-shadow:0 0 0 3px rgba(139,147,255,.16)}
input[type=text]{width:162px}.num{width:66px}
button{cursor:pointer}button:hover{border-color:var(--acc);color:var(--ink);background:var(--surf2)}
label{color:var(--mut);font-size:12px;display:flex;gap:5px;align-items:center}
.wrap{padding:16px 22px 64px;max-width:1520px}.count{color:var(--mut);margin:4px 0 12px;font-size:12px}
table{border-collapse:separate;border-spacing:0;width:100%}
th,td{padding:8px 11px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mut);font-weight:600;cursor:pointer;font-size:11px;text-transform:uppercase;letter-spacing:.04em;background:var(--bg2)}
#browse th{position:sticky;top:57px;z-index:2}
tbody tr{transition:background .1s}tr:hover td{background:var(--surf)}
.r{text-align:right;font-variant-numeric:tabular-nums}
.rar{color:var(--acc)}.nm{font-weight:600;cursor:pointer}.nm:hover{color:var(--acc)}.mut{color:var(--mut)}
.deal{color:var(--pos);font-weight:700}
.pill{background:rgba(139,147,255,.13);border:1px solid rgba(139,147,255,.32);color:#b9beff;border-radius:20px;padding:2px 9px;font-size:11px;font-weight:600}
.addb{cursor:pointer;padding:2px 9px;font-size:11px;margin-left:4px;border:1px solid var(--line2);border-radius:8px;color:var(--mut);display:inline-block;transition:.12s}
.addb:hover{border-color:var(--acc);color:var(--acc);background:rgba(139,147,255,.09)}
.qbtn{cursor:pointer;padding:0 9px;color:var(--acc);font-weight:700;user-select:none}
.x{cursor:pointer;color:var(--mut);padding:0 4px}.x:hover{color:var(--dang)}
.empty{color:var(--mut);padding:28px 4px}
.bar{display:flex;gap:8px;margin:16px 0;flex-wrap:wrap}
.warn{background:linear-gradient(90deg,rgba(234,184,106,.1),transparent);border-left:3px solid var(--warn);color:#e7d3a8;padding:9px 22px;font-size:12px}
.warn b{color:var(--warn)}
.hide{display:none}
.addres{margin:4px 0 12px;display:flex;flex-wrap:wrap;gap:7px}
.ares{display:inline-flex;align-items:center;gap:7px;background:var(--surf);border:1px solid var(--line2);border-radius:20px;padding:5px 13px;cursor:pointer;font-size:12px;transition:.12s}
.ares:hover{border-color:var(--acc);background:rgba(139,147,255,.09)}.ares .nm{font-weight:600}
.own{color:var(--pos);font-weight:700}
.deckstats{background:linear-gradient(180deg,var(--surf),var(--bg2));border:1px solid var(--line);border-radius:12px;padding:11px 16px;margin:10px 0 6px;font-size:12px}
.sec{font-size:14px;margin:22px 0 8px;color:var(--ink);font-weight:700;letter-spacing:-.01em;display:flex;align-items:center;gap:9px}
.sec::before{content:"";width:3px;height:15px;background:var(--acc);border-radius:2px}
#ov{position:fixed;inset:0;background:rgba(4,6,12,.72);backdrop-filter:blur(5px);display:none;align-items:center;justify-content:center;z-index:40;padding:20px}
.modal{background:var(--surf);border:1px solid var(--line2);border-radius:18px;max-width:600px;width:100%;max-height:88vh;overflow:auto;padding:24px 26px;box-shadow:var(--sh)}
.modal h2{margin:0 0 3px;font-size:21px;letter-spacing:-.01em}.modal .sub{color:var(--mut);font-size:12px;margin-bottom:12px}
.modal .tx{background:var(--bg2);border:1px solid var(--line);border-radius:11px;padding:12px 15px;font-size:13px;line-height:1.65;white-space:pre-wrap;margin:12px 0}
.modal table{margin:8px 0}.close{float:right;cursor:pointer;color:var(--mut);font-size:22px;line-height:1}.close:hover{color:var(--ink)}
.cimg{float:right;width:148px;border-radius:10px;margin:2px 0 12px 16px;border:1px solid var(--line2);box-shadow:var(--sh)}
.lowtag{font-size:9px;color:var(--gold);font-weight:700;white-space:nowrap}
.rsets{font-size:10px;color:#8390b3;margin-top:2px;line-height:1.3;max-width:330px;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.ana{max-width:860px}.ana h2{font-size:15px;margin:28px 0 4px;font-weight:700}.ana .ins{color:var(--mut);font-size:12px;margin:0 0 12px;line-height:1.6}
.ovw{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}
.ost{background:linear-gradient(180deg,var(--surf),var(--bg2));border:1px solid var(--line);border-radius:13px;padding:13px 17px;min-width:122px}
.ost .v{font-size:20px;font-weight:700}.ost .l{color:var(--mut);font-size:11px;margin-top:2px}
.crow{display:flex;align-items:center;gap:10px;padding:3px 0}
.clab{width:205px;font-size:12px;text-align:right;color:#c3ccdb;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cbarwrap{flex:1;background:var(--bg2);border-radius:6px;height:17px;overflow:hidden}
.cbar{background:linear-gradient(90deg,var(--acc2),var(--acc));height:100%;border-radius:6px;min-width:3px}
.cval{width:122px;font-size:12px;font-variant-numeric:tabular-nums}.cn{color:var(--mut);font-size:10px}
.hist{display:flex;align-items:flex-end;gap:7px;height:160px;margin:10px 0}
.hcol{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%}
.hbarwrap{width:100%;flex:1;display:flex;align-items:flex-end}
.hbar{width:100%;background:linear-gradient(180deg,var(--acc),var(--acc2));border-radius:5px 5px 0 0;min-height:1px}
.hlab{font-size:9px;color:var(--mut);margin-top:5px;text-align:center;line-height:1.1}.hn{font-size:10px;color:#c3ccdb;font-variant-numeric:tabular-nums}
/* ===== Final Fantasy theme layer ===== */
html{background:linear-gradient(165deg,#0b1636 0%,#070c1c 55%,#05091a 100%) fixed}
body{background:transparent}
#bg{position:fixed;inset:0;z-index:-1;pointer-events:none}
#aura{position:fixed;inset:-25%;z-index:-2;pointer-events:none;opacity:.6;
  background:radial-gradient(620px 460px at 22% 28%,rgba(90,120,255,.14),transparent 60%),radial-gradient(720px 520px at 80% 72%,rgba(143,220,255,.12),transparent 62%),radial-gradient(520px 420px at 62% 18%,rgba(232,198,106,.08),transparent 60%),radial-gradient(560px 460px at 40% 85%,rgba(90,220,180,.08),transparent 60%);
  animation:aura 26s ease-in-out infinite alternate}
@keyframes aura{from{transform:translate(0,0) scale(1)}to{transform:translate(-3%,2%) scale(1.06)}}
h1,h2,.sec,.modal h2,.ost .v,.ana h2{font-family:"Cinzel",Georgia,serif}
h1{color:var(--gold);text-shadow:0 0 18px rgba(232,198,106,.35);letter-spacing:.02em}
h1::before{content:"❖";color:var(--gold);text-shadow:0 0 12px rgba(232,198,106,.6)}
header{background:linear-gradient(180deg,rgba(12,22,52,.92),rgba(8,14,34,.86));border-bottom:1px solid var(--line2);box-shadow:0 2px 22px rgba(3,8,24,.55)}
.nav{background:rgba(10,18,44,.7);border:1px solid var(--line2)}
.nav .t.on{background:linear-gradient(180deg,#26315f,#1a2247);color:var(--gold);font-weight:700;box-shadow:inset 0 0 0 1px rgba(232,198,106,.55),0 0 12px rgba(232,198,106,.22)}
.nav .t.on::before{content:"▸ ";color:var(--gold)}
.kpi,.card,.modal,.deckstats,.ost,.ares{background:linear-gradient(180deg,rgba(24,38,78,.62),rgba(14,22,50,.66));border-color:var(--line2)}
.kpi,.card,.deckstats,.ost{box-shadow:inset 0 1px 0 rgba(140,180,255,.09),var(--sh)}
.kpi.hl{border-color:rgba(110,224,160,.45)}
.controls{background:rgba(9,15,38,.6)}
input,select{background:rgba(9,16,40,.72);border-color:var(--line2)}
input:focus,select:focus{border-color:var(--acc);box-shadow:0 0 0 3px rgba(143,220,255,.18)}
button{background:linear-gradient(180deg,#1c2b56,#141f42);border:1px solid var(--line2)}
button:hover{border-color:var(--gold);color:var(--gold2);box-shadow:0 0 12px rgba(232,198,106,.2)}
th{background:rgba(9,15,38,.95);color:#9fb0d8}
tr:hover td{background:rgba(40,58,110,.3)}
.nm:hover{color:var(--gold)}
.warn{background:linear-gradient(90deg,rgba(232,198,106,.12),transparent);border-left:3px solid var(--gold);color:#f0dfac}.warn b{color:var(--gold)}
.sec{color:var(--gold)}.sec::before{background:var(--gold);box-shadow:0 0 8px rgba(232,198,106,.5)}
.addb:hover{border-color:var(--gold);color:var(--gold2);background:rgba(232,198,106,.08)}
.qbtn{color:var(--acc)}
.cbar{background:linear-gradient(90deg,#5566d8,var(--acc))}.hbar{background:linear-gradient(180deg,var(--acc),#5566d8)}
.cimg{box-shadow:0 0 26px rgba(126,182,255,.28),var(--sh)}
.r-common{color:#9fb0c8}.r-rare{color:#7fb0ff}.r-super{color:#cdd8ea}.r-ultra{color:var(--gold)}.r-secret{color:#c58bff}
.r-holo{background:linear-gradient(90deg,#8fe0ff,#c58bff,#f3dd94);-webkit-background-clip:text;background-clip:text;color:transparent;font-weight:700}
/* ===== main menu ===== */
.menuwrap{max-width:660px;margin:0 auto;padding:60px 24px 80px;text-align:center}
.mtitle{font-family:"Cinzel",serif;font-size:clamp(30px,5vw,46px);font-weight:700;color:var(--gold);text-shadow:0 0 34px rgba(232,198,106,.4);letter-spacing:.07em}
.mtag{color:var(--acc);font-size:13px;letter-spacing:.3em;text-transform:uppercase;margin:8px 0 36px;opacity:.85}
.menugrid{display:flex;flex-direction:column;gap:11px;text-align:left}
.mgh{font-family:"Cinzel",serif;font-size:12px;text-transform:uppercase;letter-spacing:.11em;color:var(--gold);margin:12px 2px -2px;display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.mgh:first-child{margin-top:0}
.mgs{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;text-transform:none;letter-spacing:0;color:var(--mut);font-size:11px;font-weight:400}
.qstart{position:relative;background:linear-gradient(120deg,rgba(232,198,106,.12),rgba(143,220,255,.05));border:1px solid rgba(232,198,106,.32);border-radius:14px;padding:15px 20px 16px;margin-bottom:4px}
.qh{font-family:"Cinzel",serif;color:var(--gold);font-size:15px;font-weight:700;margin-bottom:5px}
.qp{color:#c9d4ea;font-size:12.5px;line-height:1.6;max-width:560px}
.qx{position:absolute;top:9px;right:13px;cursor:pointer;color:var(--mut);font-size:15px;line-height:1}.qx:hover{color:var(--ink)}
.qlink{cursor:pointer;color:var(--acc)}.qlink:hover{color:var(--gold)}
.pxnote{margin:20px auto 0;max-width:600px;font-size:11.5px;line-height:1.55;color:var(--mut);text-align:left;background:linear-gradient(90deg,rgba(234,184,106,.08),transparent);border-left:3px solid var(--warn);border-radius:9px;padding:10px 14px}.pxnote b{color:#e7d3a8}
.mitem{display:flex;align-items:center;gap:16px;padding:16px 20px;border:1px solid var(--line2);border-radius:13px;cursor:pointer;transition:.16s;
  background:linear-gradient(180deg,rgba(24,38,78,.55),rgba(12,20,46,.62));box-shadow:inset 0 1px 0 rgba(140,180,255,.07)}
.mitem:hover{border-color:var(--gold);box-shadow:0 0 24px rgba(232,198,106,.16),inset 0 0 0 1px rgba(232,198,106,.28);transform:translateX(5px)}
.mic{font-size:25px;width:38px;text-align:center;filter:drop-shadow(0 0 6px rgba(126,182,255,.4))}
.mt{font-family:"Cinzel",serif;font-size:18px;font-weight:700;color:var(--ink)}
.mitem:hover .mt{color:var(--gold2)}
.md{color:var(--mut);font-size:12.5px;margin-top:1px}
.marrow{margin-left:auto;color:var(--gold);font-size:20px;opacity:0;transition:.16s}
.mitem:hover .marrow{opacity:1}
.savebar{margin-top:32px;display:flex;justify-content:center;gap:24px;flex-wrap:wrap;color:var(--mut);font-size:12px;border-top:1px solid var(--line);padding-top:18px}
.savebar b{color:var(--ink);font-variant-numeric:tabular-nums}
/* ===== bank / budget ===== */
.bform{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0 4px;
  background:linear-gradient(180deg,rgba(24,38,78,.5),rgba(12,20,46,.55));border:1px solid var(--line2);border-radius:12px;padding:11px 13px}
.bform input,.bform select{background:rgba(9,16,40,.8)}
.bform .num{width:104px}
.bform button{background:linear-gradient(180deg,#26315f,#1a2247);color:var(--gold2);font-weight:600}
@media(max-width:640px){.bform{gap:6px}.bform input[type=text]{width:100%;min-width:0}.deckstats{gap:14px!important}}
.catbud{display:flex;flex-direction:column;gap:5px;max-width:640px;margin:8px 0 2px}
.cbrow{display:flex;align-items:center;gap:10px}
.cblab{width:118px;font-size:12px;color:#c3ccdb;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cbbarwrap{flex:1;background:var(--bg2);border-radius:6px;height:12px;overflow:hidden;min-width:50px}
.cbbar{background:linear-gradient(90deg,#5566d8,var(--acc));height:100%;border-radius:6px;min-width:2px;transition:.2s}
.cbspent{width:96px;font-size:11px;font-variant-numeric:tabular-nums;color:var(--mut);text-align:right}
.cbinp{width:72px}
.chlab{font-size:12px;color:var(--mut);margin:14px 0 3px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.leg{font-size:10px;color:var(--mut);display:inline-flex;align-items:center}
.leg i{width:9px;height:9px;border-radius:2px;display:inline-block;margin:0 4px 0 8px}
.leg .lp{background:var(--pos)}.leg .ls{background:#ff9aa8}
.chartwrap{background:linear-gradient(180deg,rgba(24,38,78,.4),rgba(12,20,46,.5));border:1px solid var(--line2);border-radius:12px;padding:10px 14px 6px;margin:4px 0;max-width:640px}
.bkchart{width:100%;height:auto;display:block;overflow:visible}
.bkln{fill:none;stroke:var(--acc);stroke-width:2.2;stroke-linejoin:round;stroke-linecap:round}
.bkarea{fill:rgba(143,220,255,.12);stroke:none}
.bkchart circle{fill:var(--acc);stroke:#0b1330;stroke-width:1}
.zl{stroke:var(--line2);stroke-width:1;stroke-dasharray:3 4}
.chxlab{display:flex;justify-content:space-between;color:var(--mut);font-size:10px;margin-top:3px}
.bkbars{display:flex;align-items:flex-end;gap:8px;height:140px;margin:6px 0 2px;padding:0 2px;overflow-x:auto;max-width:640px}
.bkbcol{flex:1;min-width:30px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%}
.bkpair{display:flex;align-items:flex-end;justify-content:center;gap:4px;width:100%;flex:1}
.bkb{width:40%;max-width:20px;border-radius:4px 4px 0 0;min-height:2px;transition:.2s}
.bkblab{font-size:9.5px;color:var(--mut);margin-top:5px;white-space:nowrap}
.trend{background:linear-gradient(90deg,rgba(143,220,255,.09),transparent);border-left:3px solid var(--acc);border-radius:10px;padding:11px 15px;margin:8px 0;font-size:12.5px;line-height:1.65;color:#c9d4ea;max-width:640px}
.trend b{color:var(--ink)}
.grp{border:1px solid var(--line2);border-radius:13px;margin:11px 0;overflow:hidden;background:linear-gradient(180deg,rgba(20,32,66,.4),rgba(11,18,42,.45));box-shadow:inset 0 1px 0 rgba(140,180,255,.06)}
.grphd{display:flex;align-items:center;gap:11px;padding:13px 17px;cursor:pointer;user-select:none;transition:.15s}
.grphd:hover{background:rgba(40,58,110,.28)}
.grpchev{color:var(--gold);font-size:11px;transition:transform .18s;width:11px;display:inline-block;text-align:center}
.grp.fold .grpchev{transform:rotate(-90deg)}
.grptt{font-family:"Cinzel",Georgia,serif;font-weight:700;color:var(--gold);font-size:14px}
.grpsub{color:var(--mut);font-size:11px;margin-left:auto;font-variant-numeric:tabular-nums}
.grpbody{padding:4px 17px 17px}
.grp.fold .grpbody{display:none}
.edrow td{background:rgba(143,220,255,.06)}
.edrow input,.edrow select{font-size:12px;padding:5px 7px}
.edrow input[type=text]{width:100%;min-width:80px}
.edrow input[type=date]{width:130px}
.simhand{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0 6px}
.simcard{width:98px;background:linear-gradient(180deg,rgba(24,38,78,.6),rgba(12,20,46,.66));border:1px solid var(--line2);border-radius:10px;padding:7px;cursor:pointer;transition:.14s;text-align:center}
.simcard:hover{border-color:var(--gold);transform:translateY(-3px);box-shadow:0 7px 20px rgba(3,8,24,.55)}
.simcard img{width:100%;border-radius:6px;display:block;margin-bottom:5px;aspect-ratio:59/86;object-fit:cover;background:var(--bg2)}
.simnm{font-size:10.5px;line-height:1.25;color:#d7deee;max-height:39px;overflow:hidden}
.simrole{font-size:9.5px;font-weight:700;margin-top:3px;text-transform:uppercase;letter-spacing:.04em}
.oddsgrid{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0}
.oddscard{background:linear-gradient(180deg,rgba(24,38,78,.6),rgba(12,20,46,.66));border:1px solid var(--line2);border-radius:12px;padding:12px 16px;min-width:148px}
.oddspct{font-size:24px;font-weight:800;font-family:"Cinzel",serif;line-height:1.1}
.oddslab{font-size:12px;color:#c3ccdb;margin-top:3px}.oddssub{font-size:10.5px;color:var(--mut);margin-top:2px}
.distrow{display:flex;align-items:flex-end;gap:12px;height:120px;margin:6px 0;max-width:360px}
.distcol{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%}
.distbarw{width:100%;flex:1;display:flex;align-items:flex-end}
.distbar{width:100%;background:linear-gradient(180deg,var(--pos),#3ba876);border-radius:5px 5px 0 0;min-height:2px}
.distn{font-size:11px;color:#c3ccdb;margin-top:4px;font-variant-numeric:tabular-nums}
.distlab{font-size:10px;color:var(--mut);margin-top:1px}
/* solo board */
.btoolbar{position:sticky;top:57px;z-index:5;display:flex;flex-wrap:wrap;align-items:center;gap:5px;background:linear-gradient(180deg,rgba(24,38,78,.96),rgba(14,22,50,.96));border:1px solid var(--gold);border-radius:11px;padding:8px 11px;margin:10px 0;box-shadow:0 6px 20px rgba(2,6,20,.5)}
.btoolbar button{font-size:11px;padding:5px 9px}
.btsel{font-weight:700;color:var(--gold2);font-size:12px}
.btsep{width:1px;height:16px;background:var(--line2);margin:0 3px}
.btoolbar button.bon{background:var(--gold);color:#1a1300;border-color:var(--gold);font-weight:700}
.bctrl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
.bhint{font-size:11.5px;color:var(--mut);margin:8px 0 2px}
.bfield{display:flex;flex-direction:column;gap:7px;margin:6px auto 0;max-width:720px;background:radial-gradient(ellipse at 50% 38%,rgba(30,46,96,.35),rgba(8,13,32,.42));border:1px solid var(--line2);border-radius:14px;padding:12px}
.bemzrow{display:grid;grid-template-columns:repeat(5,1fr);gap:7px;padding:0 79px}
.bemzrow .bslot:nth-child(1){grid-column:2}.bemzrow .bslot:nth-child(2){grid-column:4}
.bmainrow{display:flex;gap:7px;align-items:stretch}
.bzones{flex:1;display:grid;grid-template-columns:repeat(5,1fr);gap:7px}
.bside{width:72px;flex:none;display:flex;align-items:center;justify-content:center}
.bbanrow{display:flex;justify-content:flex-end;padding-right:2px}
.bslot{border:1px dashed var(--line2);border-radius:9px;aspect-ratio:59/86;display:flex;align-items:center;justify-content:center;position:relative;cursor:pointer;transition:.12s;background:rgba(12,20,46,.35);overflow:visible}
.bside .bslot{width:72px}
.bslot.bempty:hover{border-color:var(--acc)}
.bslot.bdrop{border-color:var(--gold);border-style:solid;box-shadow:0 0 0 2px rgba(232,198,106,.22) inset;background:rgba(232,198,106,.06)}
.bslab{font-size:9px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut)}
.bcard{width:100%;height:100%;border-radius:7px;overflow:hidden;position:relative;border:1px solid var(--line2);background:linear-gradient(160deg,#1a2547,#0e1730);transition:.1s}
.bcard img{width:100%;height:100%;object-fit:cover;display:block}
.bcard .bnm{display:none;position:absolute;inset:0;align-items:center;justify-content:center;text-align:center;font-size:8px;padding:3px;color:#aeb9d6;line-height:1.15}
.bcard.bnoart .bnm{display:flex}.bcard.bnoart img{display:none}
.bcard.bsel{border-color:var(--gold);box-shadow:0 0 0 2px var(--gold),0 4px 12px rgba(232,198,106,.4);z-index:3}
.bcard.bdef{transform:rotate(90deg) scale(.68)}
.bback{width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:20px;color:var(--gold);background:linear-gradient(135deg,#2a2350,#3a2d63);text-shadow:0 0 10px rgba(232,198,106,.5);border-radius:7px}
.bpile{width:72px;cursor:pointer;text-align:center}
.bpile .bptop{aspect-ratio:59/86;border:1px solid var(--line2);border-radius:9px;overflow:hidden;display:flex;align-items:center;justify-content:center;background:rgba(12,20,46,.5)}
.bpile.bempty .bptop{border-style:dashed;background:rgba(12,20,46,.3)}
.bpile:hover .bptop{border-color:var(--acc)}
.bpile .bptop .bcard,.bpile .bptop .bback{width:100%;height:100%}
.bpcount{font-size:9px;color:var(--mut);margin-bottom:3px;text-transform:uppercase;letter-spacing:.04em}
.bhandwrap{margin-top:10px;border:1px solid var(--line2);border-radius:11px;padding:8px 10px;background:linear-gradient(180deg,rgba(24,38,78,.5),rgba(12,20,46,.55))}
.bhlab{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin-bottom:6px}
.bhcards{display:flex;flex-wrap:wrap;gap:7px}
.bhcards>div{width:58px;aspect-ratio:59/86;cursor:pointer}
.bviewer{position:fixed;inset:0;background:rgba(4,8,20,.72);z-index:50;display:flex;align-items:center;justify-content:center;padding:20px}
.bvbox{background:linear-gradient(180deg,#141f42,#0c1430);border:1px solid var(--gold);border-radius:14px;max-width:840px;width:100%;max-height:82vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(2,6,20,.7)}
.bvhead{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid var(--line2)}
.bvcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:9px;padding:14px;overflow:auto}
.bvcard{aspect-ratio:59/86;border-radius:7px;overflow:hidden;position:relative;cursor:pointer;border:1px solid var(--line2);background:linear-gradient(160deg,#1a2547,#0e1730);transition:.1s}
.bvcard:hover{border-color:var(--gold);transform:translateY(-2px)}
.bvcard img{width:100%;height:100%;object-fit:cover;display:block}
.bvcard .bnm{display:none;position:absolute;inset:0;align-items:center;justify-content:center;text-align:center;font-size:8px;padding:3px;color:#aeb9d6;line-height:1.15}
.bvcard.bnoart .bnm{display:flex}.bvcard.bnoart img{display:none}
.simcard.drawn{border-color:var(--gold);box-shadow:0 0 0 1px rgba(232,198,106,.4),0 6px 16px rgba(3,8,24,.5)}
.simtags{display:flex;gap:3px;justify-content:center;margin-top:4px;flex-wrap:wrap}
.simtag{width:8px;height:8px;border-radius:50%;display:inline-block}
.simsep{display:flex;align-items:center;align-self:stretch;padding:0 2px}
.simsep span{writing-mode:vertical-rl;transform:rotate(180deg);font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:var(--gold);opacity:.8}
.tchips{display:flex;flex-wrap:wrap;gap:4px}
.tchip{font-size:10.5px;padding:2px 8px;border:1px solid var(--line2);border-radius:20px;cursor:pointer;color:var(--mut);user-select:none;transition:.12s;white-space:nowrap}
.tchip:hover{border-color:var(--acc);color:var(--ink)}
.tchip.on{font-weight:700}
.cnum{width:58px}
.combobuild{background:linear-gradient(180deg,rgba(24,38,78,.5),rgba(12,20,46,.55));border:1px solid var(--line2);border-radius:12px;padding:12px 14px}
.comboreq{display:flex;align-items:center;gap:8px;margin:6px 0}
.comboreq select{flex:1;min-width:120px;max-width:320px}
.comborow{display:flex;align-items:center;gap:12px;padding:9px 4px;border-bottom:1px solid var(--line)}
.comborow:last-child{border:0}
.combop{font-size:19px;font-weight:800;font-family:"Cinzel",serif;color:var(--acc);width:74px;text-align:right;font-variant-numeric:tabular-nums}
.combonm{font-weight:600;color:var(--ink);font-size:13px}
.playstat{display:flex;align-items:center;gap:16px;background:linear-gradient(90deg,rgba(110,224,160,.14),rgba(143,220,255,.04));border:1px solid rgba(110,224,160,.38);border-radius:13px;padding:14px 18px;margin-bottom:12px}
.playpct{font-size:30px;font-weight:800;font-family:"Cinzel",serif;color:var(--pos);line-height:1}
.playlab{font-size:14px;font-weight:700;color:var(--ink)}
.playchk{display:flex;align-items:center;cursor:pointer;flex:none}
.playchk input{width:15px;height:15px;accent-color:var(--pos);cursor:pointer}
.wrrow{display:flex;align-items:center;gap:10px;padding:4px 0;max-width:660px}
.wrlab{width:158px;text-align:right;font-size:12px;color:#c3ccdb;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wrtrack{flex:1;background:rgba(255,107,129,.26);border-radius:6px;height:16px;overflow:hidden;min-width:60px}
.wrwin{background:linear-gradient(90deg,#3ba876,var(--pos));height:100%;border-radius:6px 0 0 6px;transition:.2s}
.wrval{width:112px;font-size:11.5px;color:var(--mut);font-variant-numeric:tabular-nums}.wrval b{color:var(--ink)}
.gnum{width:44px;text-align:center}
.pips{display:flex;gap:4px;margin-top:4px}
.pip{width:11px;height:11px;border-radius:3px;display:inline-block}
.improw{display:flex;align-items:baseline;gap:12px;padding:7px 2px;border-bottom:1px solid var(--line);max-width:660px}
.improw:last-of-type{border:0}
.impnm{width:168px;font-weight:600;color:var(--ink);font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:none}
.impstat{font-size:12px;color:var(--mut)}
.needdot{color:var(--warn);margin-right:5px;font-size:9px;vertical-align:middle}
.unowned td.nm{color:#e7d3a8}
.vtog{display:inline-flex;border:1px solid var(--line2);border-radius:9px;overflow:hidden}
.vt{padding:6px 10px;cursor:pointer;font-size:13px;color:var(--mut);background:rgba(9,16,40,.5);transition:.12s;user-select:none}
.vt:hover{color:var(--ink)} .vt.on{background:linear-gradient(180deg,#26315f,#1a2247);color:var(--gold)}
.setrow{cursor:pointer}.setrow:hover .nm{color:var(--gold)}
.mpaste summary{cursor:pointer;font-size:12px;color:var(--mut);padding:3px 0}.mpaste summary:hover{color:var(--ink)}
.mpaste textarea{width:100%;max-width:540px;height:82px;margin-top:6px;background:rgba(9,16,40,.72);color:var(--ink);border:1px solid var(--line2);border-radius:9px;padding:8px;font:inherit;font-size:12px;resize:vertical}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px;margin-top:6px}
.gcard{background:linear-gradient(180deg,rgba(24,38,78,.5),rgba(12,20,46,.58));border:1px solid var(--line2);border-radius:11px;padding:7px;display:flex;flex-direction:column;gap:5px}
.gcard.unowned{border-color:rgba(232,198,106,.5)}
.gimgwrap{position:relative;aspect-ratio:59/86;border-radius:7px;overflow:hidden;cursor:pointer;background:linear-gradient(160deg,#1a2547,#0e1730)}
.gimg{width:100%;height:100%;object-fit:cover;display:block}
.gph{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;text-align:center;padding:8px;font-size:11px;color:#9fb0d6;line-height:1.3;font-family:"Cinzel",Georgia,serif;pointer-events:none}
.gimgwrap:not(.noart) .gph{display:none}
.gqty{position:absolute;top:4px;right:4px;background:rgba(6,10,26,.85);border:1px solid var(--line2);border-radius:7px;padding:1px 7px;font-size:11px;font-weight:700;font-variant-numeric:tabular-nums}
.gneed{position:absolute;top:4px;left:4px;background:rgba(232,198,106,.92);color:#0b1330;border-radius:7px;padding:1px 6px;font-size:10px;font-weight:800}
.gname{font-size:11.5px;font-weight:600;color:#e7ecfa;line-height:1.25;cursor:pointer;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;min-height:29px}
.gname:hover{color:var(--gold)}
.gmeta{display:flex;justify-content:space-between;font-size:11px;color:#c3ccdb;font-variant-numeric:tabular-nums}
.gact{display:flex;align-items:center;gap:3px;flex-wrap:wrap}
.gqn{font-size:11px;min-width:13px;text-align:center;font-variant-numeric:tabular-nums}
.gsp{flex:1}
.gab{cursor:pointer;font-size:10px;padding:1px 5px;border:1px solid var(--line2);border-radius:6px;color:var(--mut);transition:.12s}
.gab:hover{border-color:var(--gold);color:var(--gold2)}
.grar{font-size:10px;padding:2px 4px;flex:1;min-width:0}
.ovin{width:72px;text-align:right;font-size:11px;padding:4px 6px}
.ovin.ovset{border-color:var(--gold);color:var(--gold2);font-weight:700}
</style></head><body><canvas id="bg"></canvas><div id="aura"></div>
<header><h1 onclick="go('menu')" style="cursor:pointer" title="main menu">&lt;CYBERSE&gt;</h1>
<div class="nav">
  <div class="t on" data-v="menu" onclick="go('menu')">Menu</div>
  <div class="t" data-v="browse" onclick="go('browse')">Browse</div>
  <div class="t" data-v="deck" onclick="go('deck')">Deck</div>
  <div class="t" data-v="collection" onclick="go('collection')">Collection</div>
  <div class="t" data-v="wishlist" onclick="go('wishlist')">Wishlist</div>
  <div class="t" data-v="bank" onclick="go('bank')">Bank</div>
  <div class="t" data-v="sim" onclick="go('sim')">Playtest</div>
  <div class="t" data-v="plog" onclick="go('plog')">Log</div>
  <div class="t" data-v="sets" onclick="go('sets')">Sets</div>
  <div class="t" data-v="meta" onclick="go('meta')">Meta</div>
  <div class="t" data-v="analytics" onclick="go('analytics')">Analytics</div>
</div>
<div class="kpis">
  <div class="kpi"><div class="v" id="kColl">$0</div><div class="l">Collection</div></div>
  <div class="kpi"><div class="v" id="kDeck">$0</div><div class="l">Deck</div></div>
  <div class="kpi hl"><div class="v" id="kComp">$0</div><div class="l">To finish</div></div>
  <div class="kpi"><div class="v" id="kWish">$0</div><div class="l">Wishlist</div></div>
</div></header>

<div id="menu"><div class="menuwrap">
  <div class="mtitle">&lt;CYBERSE&gt;</div>
  <div class="mtag">Your Yu-Gi-Oh! Bank · Budget · Collect · Analyze · Dominate</div>
  <div class="menugrid" id="menugrid"></div>
  <div class="savebar" id="savebar"></div>
  <div class="pxnote">Heads up: prices come from a free community feed (YGOPRODeck) and are <b>estimates</b> — many printings aren't priced, and new sets lag. For cards you own, set your own value in the <b>Unit</b> column of your Collection; that flows into every total.</div>
</div></div>

<div id="browse" class="hide">
<div class="controls">
  <input type="text" id="q" placeholder="search name…" oninput="rB()">
  <input type="text" id="qa" placeholder="archetype…" oninput="rB()">
  <select id="rar" onchange="rB()"></select>
  <select id="cl" onchange="rB()"><option value="">class: all</option><option>Monster</option><option>Spell</option><option>Trap</option></select>
  <select id="bn" onchange="rB()"><option value="">ban: all</option><option>Unlimited</option><option>Semi-Limited</option><option>Limited</option><option>Forbidden</option></select>
  <label>$ min <input class="num" id="pmin" oninput="rB()"></label>
  <label>$ max <input class="num" id="pmax" oninput="rB()"></label>
  <label><input type="checkbox" id="deal" onchange="rB()"> gap deals</label>
</div>
<div class="wrap"><div class="count" id="cnt"></div>
<table><thead><tr>
<th onclick="S('n')">Card</th><th onclick="S('cl')">Class</th><th onclick="S('bn')">Ban</th>
<th onclick="S('ar')">Archetype</th><th onclick="S('hr')">Top rarity</th><th class="r" onclick="S('ag')">Age</th>
<th class="r" onclick="S('own')" title="how many you own">Own</th>
<th class="r" onclick="S('m')">Market $</th><th class="r rar" id="ph" onclick="S('rarity')">Rarity $</th>
<th class="r" onclick="S('gap')">Gap×</th><th>Add</th></tr></thead><tbody id="tb"></tbody></table></div>
</div>

<div id="list" class="hide"><div class="wrap"><div id="lctrl" class="controls" style="padding:0 0 8px;border:0"></div><div id="addres" class="addres"></div><div id="ltbl"></div>
<div class="bar" style="margin-top:14px"><button onclick="impList.click()" title="deck view: loads a new deck; collection/wishlist: merges in">Import .ydk / list</button>
<button onclick="exYdk()">Export active deck .ydk</button><button onclick="exJson()">Backup all (.json)</button>
<button onclick="imp.click()">Import backup .json</button>
<input id="impList" type="file" accept=".ydk,.txt" class="hide" onchange="importList(event)">
<input id="imp" type="file" accept=".json" class="hide" onchange="imJson(event)"></div></div></div>

<div id="analytics" class="hide"><div class="wrap" id="anaBody"></div></div>

<div id="bank" class="hide"><div class="wrap" id="bankBody"></div></div>
<div id="sim" class="hide"><div class="wrap" id="simBody"></div></div>
<div id="plog" class="hide"><div class="wrap" id="plogBody"></div></div>
<div id="sets" class="hide"><div class="wrap" id="setsBody"></div></div>
<div id="meta" class="hide"><div class="wrap" id="metaBody"></div><input id="metaFile" type="file" accept=".ydk,.txt" multiple class="hide" onchange="metaImport(event)"></div>

<div id="ov" onclick="if(event.target.id==='ov')closeM()"><div class="modal" id="mBody"></div></div>

<script>
var CARDS=__DATA__, RAR=__RAR__, ORD={}; RAR.forEach(function(r,i){ORD[r]=i;});
var SETS=__SETS__;
var BY={}; CARDS.forEach(function(c){BY[c.i]=c;});
var PRICED=CARDS.filter(function(c){return c.m!=null&&c.m>0;});
var NAME2ID={}; CARDS.forEach(function(c){NAME2ID[c.n.toLowerCase()]=c.i;});
var KEY="ygo_builder_v1", view="browse", sk="m", sd=-1, LIMIT=250;
var St=load();
function bl(){return {decks:{"Main deck":{main:{},extra:{},side:{}}},active:"Main deck",collection:{},wishlist:{},bank:{budget:0,tx:[],catBudgets:{}},roles:{},draws:{},combos:[],log:[],meta:[]};}
function load(){var s;try{s=JSON.parse(localStorage.getItem(KEY));}catch(e){}
  if(!s)return bl();
  if(s.deck&&!s.decks){s.decks={"Main deck":s.deck};s.active="Main deck";delete s.deck;}   // migrate single-deck
  if(!s.decks||!Object.keys(s.decks).length)s.decks={"Main deck":{}};
  Object.keys(s.decks).forEach(function(nm){var d=s.decks[nm];              // migrate flat decks -> main/extra/side
    if(d&&(d.main||d.extra||d.side)){d.main=d.main||{};d.extra=d.extra||{};d.side=d.side||{};}
    else{var flat=d||{},nd={main:{},extra:{},side:{}};for(var id in flat){nd[(BY[id]&&BY[id].ex)?'extra':'main'][id]=flat[id];}s.decks[nm]=nd;}});
  if(!s.active||!s.decks[s.active])s.active=Object.keys(s.decks)[0];
  if(!s.collection)s.collection={};if(!s.wishlist)s.wishlist={};
  ['collection','wishlist'].forEach(function(k){var m=s[k]||{};for(var id in m){var e=m[id];   // -> multi-line: [{rar,cond,q,ov,pr}]
    if(!Array.isArray(e))m[id]=[{rar:(e&&e.rar)||'__m',q:(e&&e.q)||1,ov:(e&&e.ov),cond:(e&&e.cond)||'',pr:(e&&e.pr)}];}s[k]=m;});
  if(!s.bank||!s.bank.tx)s.bank={budget:(s.bank&&s.bank.budget)||0,tx:(s.bank&&s.bank.tx)||[]};
  if(!s.bank.catBudgets)s.bank.catBudgets={};
  if(!s.roles)s.roles={};
  Object.keys(s.roles).forEach(function(k){if(typeof s.roles[k]==='string')s.roles[k]=[s.roles[k]];});
  if(!s.draws)s.draws={};if(!s.combos)s.combos=[];
  s.combos.forEach(function(c){if(c.play===undefined)c.play=true;});
  if(!s.log)s.log=[];
  if(!s.meta)s.meta=[];
  return s;}
function sv(){localStorage.setItem(KEY,JSON.stringify(St));}
function curDeck(){return St.decks[St.active];}
function bucket(k){return (k==='main'||k==='extra'||k==='side')?curDeck()[k]:St[k];}
function items(list){return bucket(list);}
function isMulti(list){return list==='collection'||list==='wishlist';}     // multi-line lists
function ownQ(id){var a=St.collection[id];if(!a)return 0;if(a.length!=null){var s=0;for(var i=0;i<a.length;i++)s+=a[i].q;return s;}return a.q||0;}
function lref(list,id,li){var m=bucket(list);return isMulti(list)?(m[id]?m[id][li||0]:null):m[id];}
function deckSecOf(id){return (BY[id]&&BY[id].ex)?'extra':'main';}
function newDeck(){var n=(prompt('New deck name:','')||'').trim();if(!n)return;if(!St.decks[n])St.decks[n]={main:{},extra:{},side:{}};St.active=n;sv();go('deck');}
function renDeck(){var n=(prompt('Rename deck:',St.active)||'').trim();if(!n||n===St.active)return;St.decks[n]=St.decks[St.active];delete St.decks[St.active];St.active=n;sv();go('deck');}
function delDeck(){if(Object.keys(St.decks).length<=1){alert('Keep at least one deck.');return;}if(!confirm('Delete "'+St.active+'"?'))return;delete St.decks[St.active];St.active=Object.keys(St.decks)[0];sv();go('deck');}
function pickDeck(n){St.active=n;sv();go('deck');}
function esc(s){return (s||'').replace(/[&<>]/g,function(x){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[x];});}
function f(v){return v==null?'<span class=mut>—</span>':'$'+v.toFixed(2);}
function fdate(d){if(!d)return '';var p=(''+d).split('-');if(p.length<3)return ''+d;var m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];return m[+p[1]-1]+' '+p[2].replace(/^0/,'')+', '+p[0];}
function rarClass(r){r=(r||'').toLowerCase();if(!r)return 'mut';
  if(/starlight|prismatic|ghost|ultimate|collector|quarter century/.test(r))return 'r-holo';
  if(/secret/.test(r))return 'r-secret'; if(/ultra|gold/.test(r))return 'r-ultra';
  if(/super|platinum/.test(r))return 'r-super'; if(/rare/.test(r))return 'r-rare'; return 'r-common';}
function numv(x){var v=parseFloat(x);return isNaN(v)?null:v;}
function priceOf(c,rar){ if(!rar||rar==='__m'||!(rar in c.rp))return c.m; var p=c.rp[rar]; return p==null?c.m:p; }
function entPrice(e,c){ return (e&&e.ov!=null)?e.ov:priceOf(c,e?e.rar:null); }   // your override wins, else the feed
function setOv(list,id,v,li){var e=lref(list,id,li); if(!e)return; var n=parseFloat(v); if(v!==''&&!isNaN(n)&&n>=0)e.ov=n; else delete e.ov; sv(); kpis(); rTable();}

(function(){document.getElementById('rar').innerHTML='<option value="">rarity: any</option>'+
  RAR.map(function(r){return '<option>'+r+'</option>';}).join('');})();

function go(v){view=v;
  document.querySelectorAll('.nav .t').forEach(function(t){t.classList.toggle('on',t.dataset.v===v);});
  document.getElementById('menu').classList.toggle('hide',v!=='menu');
  document.getElementById('browse').classList.toggle('hide',v!=='browse');
  document.getElementById('analytics').classList.toggle('hide',v!=='analytics');
  document.getElementById('bank').classList.toggle('hide',v!=='bank');
  document.getElementById('sim').classList.toggle('hide',v!=='sim');
  document.getElementById('plog').classList.toggle('hide',v!=='plog');
  document.getElementById('sets').classList.toggle('hide',v!=='sets');
  document.getElementById('meta').classList.toggle('hide',v!=='meta');
  document.getElementById('list').classList.toggle('hide',!(v==='deck'||v==='collection'||v==='wishlist'));
  if(v==='menu'){rMenu();return;}
  if(v==='browse'){rB();return;}
  if(v==='analytics'){rA();return;}
  if(v==='bank'){renderBank();return;}
  if(v==='sim'){renderSim();return;}
  if(v==='plog'){renderLog();return;}
  if(v==='sets'){renderSets();return;}
  if(v==='meta'){renderMeta();return;}
  var ctrl='';
  if(v==='deck'){ctrl+='<select onchange="pickDeck(this.value)">'+Object.keys(St.decks).map(function(n){return '<option'+(n===St.active?' selected':'')+'>'+esc(n)+'</option>';}).join('')+'</select>'
    +'<button onclick="newDeck()">+ New deck</button><button onclick="renDeck()">Rename</button><button onclick="delDeck()">Delete</button>';}
  ctrl+='<input type="text" id="lq" placeholder="filter this '+v+'…" oninput="rTable()">';
  ctrl+='<span class=vtog><span class="vt'+(listMode==='list'?' on':'')+'" id="vtList" onclick="setListMode(\'list\')" title="list view">☰</span><span class="vt'+(listMode==='grid'?' on':'')+'" id="vtGrid" onclick="setListMode(\'grid\')" title="grid view">▦</span></span>';
  if(v==='collection'||v==='wishlist'){
    ctrl+='<select id="lclass" onchange="rTable()"><option value="all">all types</option><option>Monster</option><option>Spell</option><option>Trap</option></select>';
    ctrl+='<select id="lsort" onchange="rTable()">'+(v==='wishlist'?'<option value="pr">Priority</option>':'')
      +'<option value="name">Name A–Z</option><option value="price">Price high→low</option><option value="value">Value high→low</option><option value="qty">Quantity</option><option value="rarity">Rarity</option></select>';
  }
  ctrl+='<input type="text" id="addq" placeholder="+ add a card to this '+v+'…" oninput="addSearch()" style="margin-left:12px;width:200px;border-color:var(--acc)">';
  lctrl_.innerHTML=ctrl; document.getElementById('addres').innerHTML=''; rTable();
}
function S(k){sd=(sk===k)?-sd:1;sk=k;rB();}
function refreshAfterAdd(){if(view==='browse')rB(); else if(view==='deck'||view==='collection'||view==='wishlist'){rTable(); if(document.getElementById('addq'))addSearch();}}
function add(list,id,rar,cond){var m=bucket(list);
  if(isMulti(list)){rar=rar||'__m';cond=cond||'';var arr=m[id]||(m[id]=[]),ln=null;
    for(var i=0;i<arr.length;i++)if(arr[i].rar===rar&&(arr[i].cond||'')===cond){ln=arr[i];break;}
    if(ln)ln.q++;else arr.push({rar:rar,cond:cond,q:1});}
  else{if(m[id])m[id].q++;else m[id]={q:1,rar:'__m'};}
  sv(); kpis(); refreshAfterAdd();}
function addLine(list,id){var m=bucket(list); if(!isMulti(list))return; (m[id]||(m[id]=[])).push({rar:'__m',cond:'',q:1}); sv(); kpis(); rTable();}
function addToDeck(id){add(deckSecOf(id),id);}
function moveTo(id,from,to){var fm=bucket(from); if(!fm[id])return; var tm=bucket(to); if(tm[id])tm[id].q+=fm[id].q; else tm[id]=fm[id]; delete fm[id]; sv(); kpis(); rTable();}
function delLine(list,id,li){var m=bucket(list); if(isMulti(list)){if(m[id]){m[id].splice(li||0,1); if(!m[id].length)delete m[id];}} else delete m[id];}
function setQ(list,id,d,li){var e=lref(list,id,li); if(!e)return; e.q+=d; if(e.q<=0)delLine(list,id,li); sv(); kpis(); rTable();}
function setR(list,id,r,li){var e=lref(list,id,li); if(e){e.rar=r; sv(); kpis(); rTable();}}
function setCond(list,id,cv,li){var e=lref(list,id,li); if(e){if(cv)e.cond=cv; else delete e.cond; sv(); rTable();}}
function setP(id,pr,li){var e=lref('wishlist',id,li); if(e){e.pr=pr; sv(); rTable();}}
function del(list,id,li){delLine(list,id,li); sv(); kpis(); rTable();}
function addSearch(){var el=document.getElementById('addq'),box=document.getElementById('addres'); if(!el||!box)return;
  var vq=el.value.toLowerCase(); if(vq.length<2){box.innerHTML='';return;}
  var hits=[],i=0; for(;i<CARDS.length&&hits.length<8;i++){if(CARDS[i].n.toLowerCase().indexOf(vq)>=0)hits.push(CARDS[i]);}
  box.innerHTML=hits.map(function(c){var own=ownQ(c.i)?' · own '+ownQ(c.i):'';
    var fn=view==='deck'?'addToDeck('+c.i+')':'add(\''+view+'\','+c.i+')';
    return '<span class=ares onclick="'+fn+'"><span class=nm>'+esc(c.n)+'</span><span class=mut> '+(c.m==null?'':'$'+c.m.toFixed(2))+own+'</span> <span class=addb>+'+view+'</span></span>';}).join('');}

function lt(list){var s=0,m=bucket(list),mu=isMulti(list); for(var id in m){var c=BY[id]; if(!c)continue;
  if(mu){m[id].forEach(function(ln){var p=entPrice(ln,c); if(p!=null)s+=p*ln.q;});}
  else{var p=entPrice(m[id],c); if(p!=null)s+=p*m[id].q;}} return s;}
function deckVal(){return lt('main')+lt('extra')+lt('side');}
function comp(){var d=curDeck(),need={},rarOf={};['main','extra','side'].forEach(function(sec){for(var id in d[sec]){need[id]=(need[id]||0)+d[sec][id].q;rarOf[id]=d[sec][id].rar;}});
  var s=0; for(var id in need){var c=BY[id]; if(!c)continue; var own=ownQ(id), buy=Math.max(0,need[id]-own), p=priceOf(c,rarOf[id]); if(p!=null)s+=p*buy;} return s;}
function kpis(){document.getElementById('kColl').textContent='$'+lt('collection').toFixed(2);
  document.getElementById('kDeck').textContent='$'+deckVal().toFixed(2);
  document.getElementById('kWish').textContent='$'+lt('wishlist').toFixed(2);
  document.getElementById('kComp').textContent='$'+comp().toFixed(2);}
function dismissIntro(){localStorage.setItem('ygo_seen','1');rMenu();}
function showIntro(){localStorage.removeItem('ygo_seen');rMenu();}
function rMenu(){var dN=Object.keys(St.decks).length,cN=Object.keys(St.collection).length,wN=Object.keys(St.wishlist).length,bN=St.bank.tx.length;
  var IT={
    browse:['🔍','Browse','Search &amp; price the '+CARDS.length.toLocaleString()+'-card catalogue'],
    deck:['🃏','Decks','Build &amp; price decks — '+dN+' saved'],
    collection:['📦','Collection','Cards you own — '+cN+' entries · $'+lt('collection').toFixed(2)],
    wishlist:['⭐','Wishlist','Cards you want — '+wN+' entries'],
    sim:['🎴','Playtest','Draw opening hands &amp; opening-odds stats'],
    plog:['📊','Match Log','Locals results &amp; win-rate analytics — '+(St.log?St.log.length:0)+' logged'],
    sets:['🗂️','Sets','Browse '+(SETS?SETS.length.toLocaleString():0)+' sets — rarity mix, price stats'],
    meta:['🧠','Meta','Top decks → staples &amp; gaps — '+(St.meta?St.meta.length:0)+' decks'],
    analytics:['📈','Analytics','Market insights &amp; price analysis'],
    bank:['💰','Bank','Budget, spending &amp; sales — '+bN+' logged']};
  var groups=[['Cards &amp; decks','the everyday hub — find, build, track',['browse','deck','collection','wishlist']],
    ['Play &amp; track','test a deck, then log how it does',['sim','plog']],
    ['Market &amp; meta','scout sets, the metagame &amp; the market',['sets','meta','analytics']],
    ['Budget','money in &amp; out of the hobby',['bank']]];
  var intro=localStorage.getItem('ygo_seen')?'':'<div class=qstart><span class=qx onclick="dismissIntro()" title="dismiss">✕</span>'
    +'<div class=qh>New here? Start simple.</div><div class=qp>&lt;CYBERSE&gt; grows with you — you don’t need all of it at once. '
    +'Begin in <b>Cards &amp; decks</b>: browse cards and build a deck. Everything else — playtest odds, match log, sets, meta, budget — '
    +'is here when you want it, and it all saves automatically in your browser.</div></div>';
  var html=intro+groups.map(function(g){return '<div class=mgh>'+g[0]+' <span class=mgs>'+g[1]+'</span></div>'
    +g[2].map(function(k){var i=IT[k];return '<div class=mitem onclick="go(\''+k+'\')"><div class=mic>'+i[0]+'</div><div><div class=mt>'+i[1]+'</div><div class=md>'+i[2]+'</div></div><div class=marrow>▸</div></div>';}).join('');}).join('');
  document.getElementById('menugrid').innerHTML=html;
  document.getElementById('savebar').innerHTML='<span>Snapshot <b>__DATE__</b></span><span>Collection <b>$'+lt('collection').toFixed(2)+'</b></span><span>Decks <b>'+dN+'</b></span><span>Wishlist <b>'+wN+'</b></span><span class=qlink onclick="showIntro()">▸ quick start</span>';}

/* ===== Bank ===== */
var CATS_OUT=['Singles','Sealed Product','Locals / Entry','Accessories','Grading','Shipping','Gift / Giveaway','Other'];
var CATS_IN=['Sold','Winnings','Trade','Other'];
var bkFMonth='all',bkFCat='all';
function bankCats(dir){return dir==='in'?CATS_IN:CATS_OUT;}
function renderBankCats(){var el=document.getElementById('bkDir');if(!el)return;
  document.getElementById('bkCat').innerHTML=bankCats(el.value).map(function(c){return '<option>'+c+'</option>';}).join('');}
function bankAdd(){var amt=parseFloat(document.getElementById('bkAmt').value);
  if(!(amt>0)){alert('Enter an amount greater than 0.');return;}
  St.bank.tx.push({id:Date.now(),date:document.getElementById('bkDate').value||new Date().toISOString().slice(0,10),
    dir:document.getElementById('bkDir').value,cat:document.getElementById('bkCat').value,amt:amt,note:document.getElementById('bkNote').value.trim()});
  sv();kpis();renderBank();}
function bankDel(id){St.bank.tx=St.bank.tx.filter(function(t){return t.id!==id;});sv();kpis();renderBank();}
function setBudget(v){St.bank.budget=parseFloat(v)||0;sv();renderBank();}
function setCatBudget(cat,v){var b=St.bank.catBudgets||(St.bank.catBudgets={});var n=parseFloat(v);if(n>0)b[cat]=n;else delete b[cat];sv();renderBank();}
var bkOpen={log:true,ledger:true,budgets:false,insights:false,bycat:false,stmts:false,
  adist:true,aban:false,arar:false,aage:false,atype:false,aarch:false,
  sodds:true,scombo:false,sroles:false,
  ladd:true,lhist:true,ldeck:false,lmatch:false,limpact:false,lsplit:false,
  mdecks:true,mstaples:true,mgaps:true};
var bkEditId=null;
function bkFold(k){bkOpen[k]=!bkOpen[k];var e=document.getElementById('grp_'+k);if(e)e.classList.toggle('fold',!bkOpen[k]);}
function grp(k,title,sub,body){return '<div class="grp'+(bkOpen[k]?'':' fold')+'" id="grp_'+k+'"><div class=grphd onclick="bkFold(\''+k+'\')"><span class=grpchev>▾</span><span class=grptt>'+title+'</span>'+(sub?'<span class=grpsub>'+sub+'</span>':'')+'</div><div class=grpbody>'+body+'</div></div>';}
function eatt(s){return esc(s||'').replace(/"/g,'&quot;');}
function bankEdit(id){bkEditId=id;renderBank();}
function bankCancel(){bkEditId=null;renderBank();}
function renderBankEditCats(){var el=document.getElementById('edDir');if(!el)return;var cur=document.getElementById('edCat').value;
  document.getElementById('edCat').innerHTML=bankCats(el.value).map(function(c){return '<option'+(c===cur?' selected':'')+'>'+c+'</option>';}).join('');}
function bankSave(id){var amt=parseFloat(document.getElementById('edAmt').value);
  if(!(amt>0)){alert('Enter an amount greater than 0.');return;}
  var t=St.bank.tx.filter(function(x){return x.id===id;})[0];if(!t){bkEditId=null;renderBank();return;}
  t.date=document.getElementById('edDate').value||t.date;t.dir=document.getElementById('edDir').value;
  t.cat=document.getElementById('edCat').value;t.amt=amt;t.note=document.getElementById('edNote').value.trim();
  bkEditId=null;sv();kpis();renderBank();}
function bkMonthly(tx){var by={};tx.forEach(function(t){var k=ym(t.date);by[k]=by[k]||{i:0,o:0};if(t.dir==='out')by[k].o+=t.amt;else by[k].i+=t.amt;});
  return Object.keys(by).sort().map(function(k){return {k:k,in:by[k].i,out:by[k].o,net:by[k].i-by[k].o};});}
function slope(ys){var n=ys.length;if(n<2)return 0;var sx=0,sy=0,sxy=0,sxx=0;for(var i=0;i<n;i++){sx+=i;sy+=ys[i];sxy+=i*ys[i];sxx+=i*i;}var d=n*sxx-sx*sx;return d?(n*sxy-sx*sy)/d:0;}
function bkLine(pts){if(pts.length<2)return '<div class=ins style="color:var(--mut);padding:6px 2px">Two or more months of activity unlock your balance trend line.</div>';
  var W=560,H=150,px=10,py=14,vs=pts.map(function(p){return p.v;}).concat([0]);
  var mn=Math.min.apply(0,vs),mx=Math.max.apply(0,vs),rng=(mx-mn)||1;
  var X=function(i){return px+i/(pts.length-1)*(W-2*px);},Y=function(v){return py+(mx-v)/rng*(H-2*py);};
  var pl=pts.map(function(p,i){return X(i).toFixed(1)+','+Y(p.v).toFixed(1);}).join(' '),z=Y(0).toFixed(1);
  var dots=pts.map(function(p,i){return '<circle cx="'+X(i).toFixed(1)+'" cy="'+Y(p.v).toFixed(1)+'" r="2.6"/>';}).join('');
  var last=pts[pts.length-1].v,lx=X(pts.length-1).toFixed(1);
  return '<div class=chartwrap><svg viewBox="0 0 '+W+' '+H+'" class=bkchart>'
    +'<line x1="'+px+'" y1="'+z+'" x2="'+(W-px)+'" y2="'+z+'" class="zl"/>'
    +'<polygon class=bkarea points="'+X(0).toFixed(1)+','+z+' '+pl+' '+lx+','+z+'"/>'
    +'<polyline class=bkln points="'+pl+'"/>'+dots+'</svg>'
    +'<div class=chxlab><span>'+mName(pts[0].k)+'</span><span>balance $'+last.toFixed(0)+'</span><span>'+mName(pts[pts.length-1].k)+'</span></div></div>';}
function bkBars(monthly){if(!monthly.length)return '';
  var mx=Math.max.apply(0,monthly.map(function(m){return Math.max(m.in,m.out);}))||1;
  return '<div class=bkbars>'+monthly.map(function(m){var ih=(100*m.in/mx).toFixed(1),oh=(100*m.out/mx).toFixed(1);
    return '<div class=bkbcol><div class=bkpair><div class=bkb style="height:'+ih+'%;background:var(--pos)" title="earned $'+m.in.toFixed(2)+'"></div><div class=bkb style="height:'+oh+'%;background:#ff9aa8" title="spent $'+m.out.toFixed(2)+'"></div></div><div class=bkblab>'+mName(m.k).replace(/ 20/,' ’')+'</div></div>';}).join('')+'</div>';}
function ym(d){return (d||'').slice(0,7);}
function mName(k){var m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],p=k.split('-');return m[+p[1]-1]+' '+p[0];}
function bankBar(rows){if(!rows.length)return '<div class=ins style="color:var(--mut)">no spending in this period</div>';
  var mx=Math.max.apply(0,rows.map(function(r){return r.v;}));
  return rows.map(function(r){return '<div class=crow><div class=clab>'+esc(r.k)+'</div><div class=cbarwrap><div class=cbar style="width:'+(mx?100*r.v/mx:0).toFixed(1)+'%"></div></div><div class=cval>$'+r.v.toFixed(2)+'</div></div>';}).join('');}
function renderBank(){var tx=St.bank.tx,bud=St.bank.budget||0,now=new Date().toISOString().slice(0,7);
  var mOut=0,mIn=0,lOut=0,lIn=0;
  tx.forEach(function(t){if(t.dir==='out')lOut+=t.amt;else lIn+=t.amt; if(ym(t.date)===now){if(t.dir==='out')mOut+=t.amt;else mIn+=t.amt;}});
  var pct=bud>0?Math.min(100,100*mOut/bud):0,over=bud>0&&mOut>bud,mNet=mIn-mOut,lNet=lIn-lOut;
  var months=Array.from(new Set(tx.map(function(t){return ym(t.date);}))).sort().reverse();
  var cats=Array.from(new Set(tx.map(function(t){return t.cat;})));
  var ftx=tx.filter(function(t){return (bkFMonth==='all'||ym(t.date)===bkFMonth)&&(bkFCat==='all'||t.cat===bkFCat);}).sort(function(a,b){return a.date<b.date?1:a.date>b.date?-1:b.id-a.id;});
  var byCat={};ftx.forEach(function(t){if(t.dir==='out')byCat[t.cat]=(byCat[t.cat]||0)+t.amt;});
  var catRows=Object.keys(byCat).map(function(k){return {k:k,v:byCat[k]};}).sort(function(a,b){return b.v-a.v;});
  var byMonth={};tx.forEach(function(t){var k=ym(t.date);byMonth[k]=byMonth[k]||{i:0,o:0};if(t.dir==='out')byMonth[k].o+=t.amt;else byMonth[k].i+=t.amt;});
  var RED='#ff9aa8';
  // ---- always-visible summary ----
  var h='<div class=deckstats style="display:flex;gap:26px;flex-wrap:wrap;align-items:center">'
    +'<div><div class=mut style="font-size:11px">THIS MONTH · '+mName(now)+'</div><div style="font-size:21px;font-weight:700">$'+mOut.toFixed(2)+' <span class=mut style="font-size:12px">spent</span></div></div>'
    +'<div style="flex:1;min-width:180px"><div class=cbarwrap style="height:12px"><div class=cbar style="width:'+pct.toFixed(0)+'%;'+(over?'background:'+RED:'')+'"></div></div><div class=mut style="font-size:11px;margin-top:4px">'+(bud>0?'$'+mOut.toFixed(0)+' of $'+bud.toFixed(0)+' budget'+(over?' — over budget!':''):'set a monthly budget →')+'</div></div>'
    +'<div><div class=mut style="font-size:11px">NET THIS MONTH</div><div style="font-size:21px;font-weight:700;color:'+(mNet>=0?'var(--pos)':RED)+'">'+(mNet>=0?'+':'−')+'$'+Math.abs(mNet).toFixed(2)+'</div></div>'
    +'<label class=mut style="font-size:12px">Budget $ <input class=num id=bkBud value="'+(bud||'')+'" onchange="setBudget(this.value)"></label></div>';
  // ---- 1. Log a transaction ----
  var logBody='<div class=bform>'
    +'<input type=date id=bkDate value="'+new Date().toISOString().slice(0,10)+'">'
    +'<select id=bkDir onchange="renderBankCats()"><option value=out>Spend</option><option value=in>Income</option></select>'
    +'<select id=bkCat></select><input class=num id=bkAmt placeholder="amount">'
    +'<input type=text id=bkNote placeholder="note (optional)" style="flex:1;min-width:140px">'
    +'<button onclick="bankAdd()">+ Log</button></div>';
  h+=grp('log','Log a transaction',null,logBody);
  // ---- 2. Ledger (with inline edit) ----
  var lb='<div class=bform>'
    +'<label class=mut>Month <select onchange="bkFMonth=this.value;renderBank()"><option value=all'+(bkFMonth==='all'?' selected':'')+'>all</option>'+months.map(function(m){return '<option value="'+m+'"'+(bkFMonth===m?' selected':'')+'>'+mName(m)+'</option>';}).join('')+'</select></label>'
    +'<label class=mut>Category <select onchange="bkFCat=this.value;renderBank()"><option value=all'+(bkFCat==='all'?' selected':'')+'>all</option>'+cats.map(function(c){return '<option'+(bkFCat===c?' selected':'')+'>'+esc(c)+'</option>';}).join('')+'</select></label></div>';
  if(!ftx.length)lb+='<div class=empty>'+(tx.length?'No transactions match the filter.':'No transactions yet — log one above.')+'</div>';
  else lb+='<table><tr><th>Date</th><th>Type</th><th>Category</th><th class=r>Amount</th><th>Note</th><th></th></tr>'+ftx.map(function(t){var col=t.dir==='out'?RED:'var(--pos)';
    if(t.id===bkEditId)return '<tr class=edrow><td><input type=date id=edDate value="'+t.date+'"></td>'
      +'<td><select id=edDir onchange="renderBankEditCats()"><option value=out'+(t.dir==='out'?' selected':'')+'>Spend</option><option value=in'+(t.dir==='in'?' selected':'')+'>Income</option></select></td>'
      +'<td><select id=edCat>'+bankCats(t.dir).map(function(c){return '<option'+(c===t.cat?' selected':'')+'>'+esc(c)+'</option>';}).join('')+'</select></td>'
      +'<td class=r><input class=num id=edAmt value="'+t.amt+'"></td>'
      +'<td><input type=text id=edNote value="'+eatt(t.note)+'"></td>'
      +'<td style="white-space:nowrap"><span class=addb onclick="bankSave('+t.id+')">Save</span><span class=x onclick="bankCancel()">✕</span></td></tr>';
    return '<tr><td>'+t.date+'</td><td style="color:'+col+'">'+(t.dir==='out'?'Spend':'Income')+'</td><td>'+esc(t.cat)+'</td><td class="r" style="color:'+col+'">'+(t.dir==='out'?'−':'+')+'$'+t.amt.toFixed(2)+'</td><td class=mut>'+esc(t.note||'')+'</td><td style="white-space:nowrap"><span class=addb onclick="bankEdit('+t.id+')" title="edit">✎</span><span class=x onclick="bankDel('+t.id+')" title="delete">✕</span></td></tr>';}).join('')+'</table>';
  h+=grp('ledger','Ledger',tx.length?ftx.length+' of '+tx.length+' shown':null,lb);
  // ---- 3. Category budgets ----
  var cb=St.bank.catBudgets||{},mByCat={};
  tx.forEach(function(t){if(t.dir==='out'&&ym(t.date)===now)mByCat[t.cat]=(mByCat[t.cat]||0)+t.amt;});
  var capTot=CATS_OUT.reduce(function(s,c){return s+(cb[c]||0);},0);
  var budBody='<div class=catbud>'
    +CATS_OUT.map(function(c){var sp=mByCat[c]||0,bg=cb[c]||0,p=bg>0?Math.min(100,100*sp/bg):0,ov=bg>0&&sp>bg;
      return '<div class=cbrow><div class=cblab>'+esc(c)+'</div><div class=cbbarwrap><div class=cbbar style="width:'+p.toFixed(0)+'%;'+(ov?'background:'+RED:'')+'"></div></div><div class=cbspent'+(ov?' style="color:'+RED+'"':'')+'>$'+sp.toFixed(0)+(bg>0?' / $'+bg.toFixed(0):'')+'</div><input class="num cbinp" value="'+(bg||'')+'" placeholder="cap" onchange="setCatBudget(\''+c+'\',this.value)"></div>';}).join('')+'</div>'
    +'<div class=mut style="font-size:11px;margin-top:6px">'+(capTot>0?'Category caps total <b style="color:#c3ccdb">$'+capTot.toFixed(0)+'</b>'+(bud>0?' vs overall budget $'+bud.toFixed(0):'')+' this month.':'Set a cap on any category to track it against this month’s spend.')+'</div>';
  h+=grp('budgets','Category budgets',capTot>0?'$'+capTot.toFixed(0)+' capped':'optional',budBody);
  // ---- 4. Trends & insights ----
  var monthly=bkMonthly(tx),cum=[],run=0;monthly.forEach(function(m){run+=m.net;cum.push({k:m.k,v:run});});
  var nM=monthly.length,totOut=monthly.reduce(function(s,m){return s+m.out;},0),avgOut=nM?totOut/nM:0;
  var curRow=monthly.filter(function(m){return m.k===now;})[0],curOut=curRow?curRow.out:0;
  var vsAvg=avgOut>0?(curOut-avgOut)/avgOut*100:0,spSl=slope(monthly.map(function(m){return m.out;}));
  var colVal=lt('collection'),netInv=lOut-lIn,paper=colVal-netInv;
  var insBody;
  if(!tx.length)insBody='<div class=empty>Log a few transactions to see your trends.</div>';
  else{
    insBody='<div class=ovw>'+ost('$'+lOut.toFixed(0),'lifetime spent')+ost('$'+lIn.toFixed(0),'lifetime earned')
      +ost((lNet>=0?'+':'−')+'$'+Math.abs(lNet).toFixed(0),'net position')+ost(tx.length,'transactions')+'</div>';
    if(nM>=2){var dir=spSl>1?'rising':spSl<-1?'easing off':'holding steady',dcol=spSl>1?RED:spSl<-1?'var(--pos)':'var(--mut)';
      insBody+='<div class=trend>Across <b>'+nM+' months</b> you’ve spent <b>$'+totOut.toFixed(0)+'</b> — about <b>$'+avgOut.toFixed(0)+'/mo</b>. Your monthly spend is <b style="color:'+dcol+'">'+dir+'</b>'+(Math.abs(spSl)>=1?' (~$'+Math.abs(spSl).toFixed(0)+'/mo)':'')+'.'+(curRow?' This month sits at <b>$'+curOut.toFixed(0)+'</b>, '+(vsAvg>=0?'<b style="color:'+RED+'">'+vsAvg.toFixed(0)+'% above</b>':'<b style="color:var(--pos)">'+Math.abs(vsAvg).toFixed(0)+'% below</b>')+' your usual pace.':'')+'</div>';}
    insBody+='<div class=chlab>Net cash flow · running balance</div>'+bkLine(cum);
    insBody+='<div class=chlab>Monthly earned vs spent <span class=leg><i class=lp></i>earned<i class=ls></i>spent</span></div>'+bkBars(monthly);
    insBody+='<div class=ovw style="margin-top:10px">'+ost(nM,nM===1?'month tracked':'months tracked')+ost('$'+avgOut.toFixed(0),'avg spend / mo')+ost('$'+netInv.toFixed(0),'net cash in')+ost('$'+colVal.toFixed(0),'collection value')+ost((paper>=0?'+':'−')+'$'+Math.abs(paper).toFixed(0),'paper position')+'</div>';
    insBody+='<div class=mut style="font-size:11px;margin-top:6px;max-width:640px;line-height:1.5"><b>Paper position</b> = your collection at current market value minus the net cash you’ve put in (spend − income). Under zero is normal — entry fees, sleeves and shipping aren’t resellable, and market-low prices aren’t what you’d net selling. Collection <i>value over time</i> fills in as the price collector banks more history.</div>';
  }
  h+=grp('insights','Trends & insights',tx.length?(lNet>=0?'+':'−')+'$'+Math.abs(lNet).toFixed(0)+' net':null,insBody);
  // ---- 5. Spending by category ----
  h+=grp('bycat','Spending by category',bkFMonth==='all'?'all time':mName(bkFMonth),bankBar(catRows));
  // ---- 6. Monthly statements ----
  var stBody=!months.length?'<div class=empty>—</div>'
    :'<table><tr><th>Month</th><th class=r>Earned</th><th class=r>Spent</th><th class=r>Net</th></tr>'+months.map(function(k){var mo=byMonth[k],net=mo.i-mo.o;
    return '<tr><td>'+mName(k)+'</td><td class="r" style="color:var(--pos)">$'+mo.i.toFixed(2)+'</td><td class="r" style="color:'+RED+'">$'+mo.o.toFixed(2)+'</td><td class="r" style="color:'+(net>=0?'var(--pos)':RED)+'">'+(net>=0?'+':'−')+'$'+Math.abs(net).toFixed(2)+'</td></tr>';}).join('')+'</table>';
  h+=grp('stmts','Monthly statements',months.length?months.length+(months.length===1?' month':' months'):null,stBody);
  document.getElementById('bankBody').innerHTML=h; renderBankCats();}

/* ===== Playtest simulator ===== */
var TAGS=[['starter','Starter','#6ee0a0'],['extender','Extender','#8fdcff'],['handtrap','Handtrap','#c58bff'],['breaker','Board Breaker','#e8c66a'],['brick','Brick','#ff9aa8'],['draw','Draw / Dig','#f0a0d0']];
var simDeck=null,simGo='first',simOrder=null,simSeen=0;
var comboDraft={reqs:[{sel:'any',count:1}]};
function tagLabel(t){for(var i=0;i<TAGS.length;i++)if(TAGS[i][0]===t)return TAGS[i][1];return t;}
function tagColor(t){for(var i=0;i<TAGS.length;i++)if(TAGS[i][0]===t)return TAGS[i][2];return 'var(--mut)';}
function cardTags(id){var r=St.roles[id];return Array.isArray(r)?r:(r?[r]:[]);}
function toggleTag(id,t){var r=cardTags(id).slice(),i=r.indexOf(t);if(i>=0)r.splice(i,1);else r.push(t);if(r.length)St.roles[id]=r;else delete St.roles[id];sv();renderSim();}
function setDraws(id,v){var n=parseInt(v,10);if(n>0)St.draws[id]=n;else delete St.draws[id];sv();renderSim();}
function simName(){return simDeck&&St.decks[simDeck]?simDeck:St.active;}
function simMainList(){var d=St.decks[simName()];if(!d)return [];var a=[];for(var id in d.main){for(var k=0;k<d.main[id].q;k++)a.push(+id);}return a;}
function simUniq(){var d=St.decks[simName()];if(!d)return [];return Object.keys(d.main).map(function(id){return {id:+id,q:d.main[id].q};});}
function shuffle(a){a=a.slice();for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),t=a[i];a[i]=a[j];a[j]=t;}return a;}
function nOpen(){return simGo==='first'?5:6;}
function drawHand(){var deck=simMainList();simOrder=deck.length?shuffle(deck):[];simSeen=Math.min(nOpen(),simOrder.length);renderSim();}
function drawNext(){if(simOrder&&simSeen<simOrder.length){simSeen++;renderSim();}}
function comb(nn,kk){if(kk<0||kk>nn)return 0;if(kk===0||kk===nn)return 1;kk=Math.min(kk,nn-kk);var r=1;for(var i=0;i<kk;i++)r=r*(nn-i)/(i+1);return r;}
function hypP0(N,K,n){if(K<=0)return 1;var p=1;for(var i=0;i<n;i++){p*=(N-K-i)/(N-i);if(p<0)p=0;}return p;}
function hypPmf(N,K,n,x){return comb(K,x)*comb(N-K,n-x)/comb(N,n);}
function simResolve(order,nStart){var seen=order.slice(0,nStart),ptr=nStart,resolved={},changed=true;
  while(changed){changed=false;for(var k=0;k<seen.length;k++){if(resolved[k])continue;var dn=St.draws[seen[k]]||0;if(dn>0){resolved[k]=true;for(var q=0;q<dn&&ptr<order.length;q++)seen.push(order[ptr++]);changed=true;}}}
  return seen;}
function cardMatches(id,sel){if(sel==='any')return true;
  if(sel==='monster')return !!(BY[id]&&BY[id].cl==='Monster');
  if(sel==='spell')return !!(BY[id]&&BY[id].cl==='Spell');
  if(sel==='trap')return !!(BY[id]&&BY[id].cl==='Trap');
  if(sel.indexOf('tag:')===0)return cardTags(id).indexOf(sel.slice(4))>=0;
  if(sel.indexOf('card:')===0)return id===+sel.slice(5);
  return false;}
function comboOK(seen,reqs){var slots=[];reqs.forEach(function(rq){for(var i=0;i<(rq.count||1);i++)slots.push(rq.sel);});
  if(!slots.length)return true;
  var adj=slots.map(function(sel){var c=[];for(var i=0;i<seen.length;i++)if(cardMatches(seen[i],sel))c.push(i);return c;});
  var mc=[];for(var i=0;i<seen.length;i++)mc.push(-1);
  function aug(s,vis){for(var x=0;x<adj[s].length;x++){var ci=adj[s][x];if(!vis[ci]){vis[ci]=1;if(mc[ci]<0||aug(mc[ci],vis)){mc[ci]=s;return true;}}}return false;}
  for(var s=0;s<slots.length;s++){var vis=[];for(var i=0;i<seen.length;i++)vis.push(0);if(!aug(s,vis))return false;}
  return true;}
function simCombo(reqs,T){var deck=simMainList();if(!deck.length)return null;var n=nOpen(),hit=0;
  for(var t=0;t<T;t++){var order=shuffle(deck);if(comboOK(simResolve(order,n),reqs))hit++;}return hit/T;}
function simTag(tag,resolve,T){var deck=simMainList();if(!deck.length)return {p1:0,avg:0};var n=nOpen(),hit=0,sum=0;
  for(var t=0;t<T;t++){var order=shuffle(deck),seen=resolve?simResolve(order,n):order.slice(0,n),c=0;for(var i=0;i<seen.length;i++)if(cardTags(seen[i]).indexOf(tag)>=0)c++;if(c>0)hit++;sum+=c;}return {p1:hit/T,avg:sum/T};}
function hasDraws(){var u=simUniq();for(var i=0;i<u.length;i++)if(St.draws[u[i].id])return true;return false;}
function selText(sel){if(sel==='any')return 'any card';if(sel==='monster')return 'any Monster';if(sel==='spell')return 'any Spell';if(sel==='trap')return 'any Trap';
  if(sel.indexOf('tag:')===0)return 'a '+tagLabel(sel.slice(4));
  if(sel.indexOf('card:')===0){var c=BY[+sel.slice(5)];return c?c.n:'a specific card';}return sel;}
function selOptions(cur){var o='';[['any','Any card'],['monster','Any Monster'],['spell','Any Spell'],['trap','Any Trap']].forEach(function(b){o+='<option value="'+b[0]+'"'+(cur===b[0]?' selected':'')+'>'+b[1]+'</option>';});
  TAGS.forEach(function(T){o+='<option value="tag:'+T[0]+'"'+(cur==='tag:'+T[0]?' selected':'')+'>Tagged: '+T[1]+'</option>';});
  simUniq().forEach(function(u){var c=BY[u.id];o+='<option value="card:'+u.id+'"'+(cur==='card:'+u.id?' selected':'')+'>Card: '+esc((c?c.n:''+u.id).slice(0,42))+'</option>';});return o;}
function comboAddReq(){comboDraft.reqs.push({sel:'any',count:1});renderSim();}
function comboDelReq(i){comboDraft.reqs.splice(i,1);if(!comboDraft.reqs.length)comboDraft.reqs.push({sel:'any',count:1});renderSim();}
function comboReqSel(i,v){comboDraft.reqs[i].sel=v;renderSim();}
function comboReqCount(i,v){comboDraft.reqs[i].count=Math.max(1,parseInt(v,10)||1);renderSim();}
function comboSave(){var nm=(document.getElementById('comboNm').value||'').trim()||('Combo '+(St.combos.length+1));
  St.combos.push({name:nm,reqs:comboDraft.reqs.map(function(r){return {sel:r.sel,count:r.count||1};}),play:true});
  comboDraft={reqs:[{sel:'any',count:1}]};sv();renderSim();}
function comboDel(idx){St.combos.splice(idx,1);sv();renderSim();}
function comboTogglePlay(idx){var cur=St.combos[idx].play!==false;St.combos[idx].play=!cur;sv();renderSim();}
function playCombos(){return St.combos.filter(function(c){return c.play!==false;});}
function simPlayable(T){var deck=simMainList();if(!deck.length)return null;var pcs=playCombos();if(!pcs.length)return null;var n=nOpen(),hit=0;
  for(var t=0;t<T;t++){var seen=simResolve(shuffle(deck),n),ok=false;for(var i=0;i<pcs.length;i++){if(comboOK(seen,pcs[i].reqs)){ok=true;break;}}if(ok)hit++;}
  return hit/T;}
var simMode='odds';
function setSimMode(m){simMode=m;renderSim();}
function renderSim(){
  var toggle='<div class=vtog style="margin:0 0 12px"><span class="vt'+(simMode==='odds'?' on':'')+'" onclick="setSimMode(\'odds\')">📊 Opening odds</span><span class="vt'+(simMode==='board'?' on':'')+'" onclick="setSimMode(\'board\')">🎴 Solo board</span></div>';
  if(simMode==='board'){renderBoard(toggle);return;}
  var name=simName(),N=simMainList().length,n=nOpen();
  var h=toggle+'<div class=deckstats style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">'
    +'<label class=mut>Deck <select onchange="simDeck=this.value;simOrder=null;renderSim()">'+Object.keys(St.decks).map(function(nm){return '<option'+(nm===name?' selected':'')+'>'+esc(nm)+'</option>';}).join('')+'</select></label>'
    +'<label class=mut>On the <select onchange="simGo=this.value;if(simOrder)simSeen=Math.min(nOpen(),simOrder.length);renderSim()"><option value=first'+(simGo==='first'?' selected':'')+'>play · draw 5</option><option value=second'+(simGo==='second'?' selected':'')+'>draw · draw 6</option></select></label>'
    +'<button onclick="drawHand()">🎴 '+(simOrder?'New hand':'Draw hand')+'</button>'
    +(simOrder&&simOrder.length?'<button onclick="drawNext()"'+(simSeen>=simOrder.length?' disabled':'')+'>＋ Draw for turn</button>':'')
    +'<span class=mut style="font-size:12px">'+N+'-card main deck'+(N<40?' <span style="color:var(--warn)">(under 40)</span>':'')+'</span></div>';
  if(simOrder){
    if(!simOrder.length)h+='<div class=empty>This deck has no Main Deck cards yet — add some in the Deck tab.</div>';
    else{var hand=simOrder.slice(0,simSeen);
      var cardHtml=function(id,extra){var c=BY[id],tg=cardTags(id);
        return '<div class="simcard'+(extra?' drawn':'')+'" onclick="openM('+id+')"><img src="data/images/'+id+'.jpg" onerror="this.style.display=\'none\'"><div class=simnm>'+esc(c?c.n:''+id)+'</div>'+(tg.length?'<div class=simtags>'+tg.map(function(t){return '<span class=simtag title="'+tagLabel(t)+'" style="background:'+tagColor(t)+'"></span>';}).join('')+'</div>':'')+'</div>';};
      h+='<div class=simhand>'+hand.slice(0,n).map(function(id){return cardHtml(id,false);}).join('')
        +(simSeen>n?'<div class=simsep><span>drew</span></div>'+hand.slice(n).map(function(id){return cardHtml(id,true);}).join(''):'')+'</div>';
      var comp={};hand.forEach(function(id){cardTags(id).forEach(function(t){comp[t]=(comp[t]||0)+1;});});
      var cs=TAGS.filter(function(T){return comp[T[0]];}).map(function(T){return '<span style="color:'+T[2]+'">'+comp[T[0]]+' '+T[1]+(comp[T[0]]>1?'s':'')+'</span>';}).join(' · ');
      h+='<div class=mut style="font-size:12px;margin:8px 0 4px">'+(simSeen>n?'Seeing <b>'+simSeen+'</b> cards ('+n+' opening + '+(simSeen-n)+' drawn). ':'')+(cs||'No tagged cards in view — tag your key cards below to light up odds.')+'</div>';}
  } else h+='<div class=mut style="font-size:12.5px;margin:12px 0;max-width:660px">Press <b>Draw hand</b> to shuffle and see an opening, then <b>Draw for turn</b> to draw the next card. Tag your key cards in <b>Card roles</b> (a card can hold several tags), then read your opening odds and build <b>combo</b> checks below.</div>';
  // ---- odds ----
  var tagCount={};simUniq().forEach(function(u){cardTags(u.id).forEach(function(t){tagCount[t]=(tagCount[t]||0)+u.q;});});
  var oddsBody;
  if(N<1)oddsBody='<div class=empty>Add cards to this deck first (Deck tab).</div>';
  else if(!Object.keys(tagCount).length)oddsBody='<div class=ins>Tag cards below — e.g. mark combo starters as “Starter”, disruption as “Handtrap”, going-second cards as “Board Breaker” — and this shows your hypergeometric opening odds: the chance to see at least one in your opening '+n+' cards.</div>';
  else{
    oddsBody='<div class=oddsgrid>'+TAGS.filter(function(T){return tagCount[T[0]];}).map(function(T){var K=tagCount[T[0]],p1=1-hypP0(N,K,n),e=n*K/N;
      return '<div class=oddscard><div class=oddspct style="color:'+T[2]+'">'+(p1*100).toFixed(1)+'%</div><div class=oddslab>open ≥1 '+T[1]+'</div><div class=oddssub>'+K+' in deck · exp '+e.toFixed(2)+'/hand</div></div>';}).join('')+'</div>';
    if(tagCount['starter']){var K=tagCount['starter'];
      var dist=[0,1,2,3].map(function(x){return x<3?hypPmf(N,K,n,x):Math.max(0,1-hypPmf(N,K,n,0)-hypPmf(N,K,n,1)-hypPmf(N,K,n,2));}),labs=['0','1','2','3+'],mx=Math.max.apply(0,dist);
      oddsBody+='<div class=chlab style="margin-top:14px">Starters in your opening hand</div><div class=distrow>'+dist.map(function(p,i){return '<div class=distcol><div class=distbarw><div class=distbar style="height:'+(mx?100*p/mx:0).toFixed(1)+'%"></div></div><div class=distn>'+(p*100).toFixed(0)+'%</div><div class=distlab>'+labs[i]+'</div></div>';}).join('')+'</div>';
      var openF=(1-hypP0(N,K,n))*100,mc=simTag('starter',false,20000);
      oddsBody+='<div class=trend style="margin-top:12px">Formula says <b>'+openF.toFixed(1)+'%</b> to open ≥1 starter; a <b>20,000-hand</b> Monte-Carlo agrees at <b>'+(mc.p1*100).toFixed(1)+'%</b> — the hypergeometric model checking out against brute force. Avg starters/opening: <b>'+mc.avg.toFixed(2)+'</b>.'
        +(hasDraws()?' With your <b>draw/dig</b> cards resolved in simulation, you effectively see one <b style="color:var(--pos)">'+(simTag('starter',true,20000).p1*100).toFixed(1)+'%</b> of the time.':'')+'</div>';}
  }
  h+=grp('sodds','Opening-hand odds',Object.keys(tagCount).length?N+' cards':null,oddsBody);
  // ---- combos ----
  var cbBody='';
  var pcs=playCombos(),pp=null;
  if(N>=1&&pcs.length){pp=simPlayable(15000);
    cbBody+='<div class=playstat><div class=playpct>'+(pp*100).toFixed(1)+'%</div><div><div class=playlab>You open a playable hand</div><div class=mut style="font-size:11px">at least one of your '+pcs.length+' checked combo'+(pcs.length>1?'s comes':' comes')+' together in your opening '+n+(hasDraws()?', draw/dig resolved':'')+'</div></div></div>';}
  cbBody+='<div class=combobuild><input type=text id=comboNm placeholder="combo name (e.g. Starter + any card)" style="min-width:210px">'
    +comboDraft.reqs.map(function(r,i){return '<div class=comboreq><span class=mut style="font-size:11px">need</span><input class=cnum type=number min=1 value="'+(r.count||1)+'" onchange="comboReqCount('+i+',this.value)"><select onchange="comboReqSel('+i+',this.value)">'+selOptions(r.sel)+'</select><span class=x onclick="comboDelReq('+i+')">✕</span></div>';}).join('')
    +'<div style="display:flex;gap:8px;margin-top:8px"><button onclick="comboAddReq()">+ Requirement</button><button onclick="comboSave()">Save combo</button></div></div>'
    +'<div class=mut style="font-size:11px;margin:8px 0 10px;max-width:648px">A combo counts as opened when your hand (draw/dig resolved) holds <b>distinct</b> cards meeting every requirement — e.g. “1 Starter + 1 any card”, or a conditional starter as “1 [that card] + 1 [its enabler spell]”. Tick the ✓ on a combo to fold it into the <b>playable-hand</b> % above (the union of your checked lines). Probabilities come from a 15,000-hand simulation.</div>';
  if(!St.combos.length)cbBody+='<div class=empty style="padding:4px 2px">No combos yet — build one above.</div>';
  else if(N<1)cbBody+='<div class=empty>Add cards to this deck first.</div>';
  else cbBody+=St.combos.map(function(cb,idx){var p=simCombo(cb.reqs,15000),desc=cb.reqs.map(function(r){return (r.count>1?r.count+'× ':'')+selText(r.sel);}).join(' + ');
    return '<div class=comborow><label class=playchk title="count toward playable-hand %"><input type=checkbox '+(cb.play!==false?'checked':'')+' onchange="comboTogglePlay('+idx+')"></label><div class=combop>'+(p==null?'—':(p*100).toFixed(1)+'%')+'</div><div style="flex:1;min-width:0"><div class=combonm>'+esc(cb.name)+'</div><div class=mut style="font-size:11px">'+esc(desc)+'</div></div><span class=x onclick="comboDel('+idx+')">✕</span></div>';}).join('');
  h+=grp('scombo','Combo consistency',pp!=null?(pp*100).toFixed(0)+'% playable':(St.combos.length?St.combos.length+(St.combos.length===1?' combo':' combos'):null),cbBody);
  // ---- roles ----
  var uniq=simUniq().sort(function(a,b){var na=BY[a.id]?BY[a.id].n:'',nb=BY[b.id]?BY[b.id].n:'';return na<nb?-1:na>nb?1:0;});
  var rolesBody=!uniq.length?'<div class=empty>No Main Deck cards yet.</div>'
    :'<div class=mut style="font-size:11px;margin-bottom:8px">Tap tags to toggle (a card can have several). “Draws” = how many extra cards you see when you activate it (draw/dig spells) — used by the odds simulation. Tags are remembered per card across decks.</div><table><tr><th>Card</th><th>Qty</th><th>Tags</th><th>Draws</th></tr>'+uniq.map(function(u){var c=BY[u.id];
      return '<tr><td class=nm onclick="openM('+u.id+')">'+esc(c?c.n:''+u.id)+'</td><td>'+u.q+'</td><td style="white-space:normal"><div class=tchips>'+TAGS.map(function(T){var on=cardTags(u.id).indexOf(T[0])>=0;return '<span class="tchip'+(on?' on':'')+'"'+(on?' style="background:'+T[2]+';border-color:'+T[2]+';color:#0b1330"':'')+' onclick="toggleTag('+u.id+',\''+T[0]+'\')">'+T[1]+'</span>';}).join('')+'</div></td><td><input class=cnum type=number min=0 value="'+(St.draws[u.id]||'')+'" placeholder="0" onchange="setDraws('+u.id+',this.value)"></td></tr>';}).join('')+'</table>';
  h+=grp('sroles','Card roles &amp; tags',uniq.length+' cards',rolesBody);
  document.getElementById('simBody').innerHTML=h;}

/* ===== Solo playtest board (DuelingBook-like: interactable piles + proper field) ===== */
var board=null, sel=null, placeMode='atk', viewer=null;
function boardNew(){var d=St.decks[simName()];if(!d){board=null;renderSim();return;}
  var deck=[];for(var id in d.main)for(var k=0;k<d.main[id].q;k++)deck.push(+id);
  var ex=[];for(var id in d.extra)for(var k=0;k<d.extra[id].q;k++)ex.push(+id);
  board={deck:shuffle(deck),ex:ex,hand:[],gy:[],ban:[],
    mon:[[],[],[],[],[]],st:[[],[],[],[],[]],emz:[[],[]],fs:[[]]};
  sel=null;viewer=null;placeMode='atk';renderSim();}
function inst(id){return {id:+id,fd:false,def:false};}
function isSlot(k){return k==='mon'||k==='st'||k==='emz'||k==='fs';}
function zArr(k,s){return isSlot(k)?board[k][s]:board[k];}
function selInst(){if(!sel||!board)return null;
  if(sel.k==='deck')return board.deck.length?inst(board.deck[sel.i]):null;
  if(sel.k==='ex')return board.ex.length?inst(board.ex[sel.i]):null;
  var a=zArr(sel.k,sel.s);return a?a[sel.i]:null;}
function selRemove(){if(!sel)return null;var it,id;
  if(sel.k==='deck'){id=board.deck.splice(sel.i,1)[0];it=inst(id);}
  else if(sel.k==='ex'){id=board.ex.splice(sel.i,1)[0];it=inst(id);}
  else{var a=zArr(sel.k,sel.s);it=a.splice(sel.i,1)[0];}
  return it;}
function place(destK,destS){var it=selRemove();if(!it){sel=null;renderSim();return;}
  if(isSlot(destK)){
    if(destK==='fs'){it.fd=false;it.def=false;}
    else if(placeMode==='set'){it.fd=true;it.def=(destK==='mon'||destK==='emz');}
    else if(placeMode==='def'){it.fd=false;it.def=true;}
    else{it.fd=false;it.def=false;}
    board[destK][destS].push(it);
  } else if(destK==='deckTop'){board.deck.unshift(it.id);}
  else if(destK==='deckBtm'){board.deck.push(it.id);}
  else if(destK==='ex'){board.ex.push(it.id);}
  else if(destK==='off'){/*removed from play*/}
  else if(destK==='hand'){it.fd=false;it.def=false;board.hand.push(it);}
  else{it.fd=false;board[destK].push(it);} /* gy, ban */
  sel=null;renderSim();}
function bSelect(k,s,i){if(sel&&sel.k===k&&sel.s===s&&sel.i===i)sel=null;else sel={k:k,s:s,i:i};viewer=null;renderSim();}
function bSlotTap(k,s){if(sel){place(k,s);return;}var a=board[k][s];if(a&&a.length)bSelect(k,s,a.length-1);}
function bFlip(){var it=selInst();if(!it)return;it.fd=!it.fd;renderSim();}
function bRot(){var it=selInst();if(!it)return;it.def=!it.def;renderSim();}
function setPlace(m){placeMode=m;renderSim();}
function bDraw(n){if(!board)return;for(var i=0;i<(n||1)&&board.deck.length;i++)board.hand.push(inst(board.deck.shift()));sel=null;renderSim();}
function bMillTop(){if(!board||!board.deck.length)return;board.gy.push(inst(board.deck.shift()));renderSim();}
function bBanishTop(){if(!board||!board.deck.length)return;board.ban.push(inst(board.deck.shift()));renderSim();}
function bShuffle(){if(!board)return;board.deck=shuffle(board.deck);sel=null;renderSim();}
function bView(v){viewer=(viewer===v)?null:v;sel=null;renderSim();}
function bCardHTML(it,seld,mini){var c=BY[it.id];
  var inner=it.fd?'<div class=bback>&#9672;</div>'
    :'<img src="data/images/'+it.id+'.jpg" onerror="this.style.display=\'none\';this.parentNode.classList.add(\'bnoart\')"><span class=bnm>'+esc(c?c.n:'')+'</span>';
  return '<div class="bcard'+(seld?' bsel':'')+(it.def?' bdef':'')+(mini?' bmini':'')+'" title="'+eatt((c?c.n:'')+(it.fd?' (face-down)':'')+(it.def?' (DEF)':''))+'">'+inner+'</div>';}
function slotHTML(k,s,label){var a=board[k][s],has=a&&a.length,seld=sel&&sel.k===k&&sel.s===s;
  var body=has?a.map(function(it,i){return bCardHTML(it,seld&&sel.i===i,false);}).join(''):'<span class=bslab>'+label+'</span>';
  return '<div class="bslot'+(has?'':' bempty')+((sel&&!has)?' bdrop':'')+'" onclick="bSlotTap(\''+k+'\','+s+')">'+body+'</div>';}
function pileHTML(k,label){var a=k==='deck'?board.deck:(k==='ex'?board.ex:board[k]),n=a.length,top;
  if((k==='gy'||k==='ban')&&n)top=bCardHTML(board[k][n-1],false,true);
  else if(n)top='<div class=bback>&#9672;</div>';
  else top='<span class=bslab>'+label+'</span>';
  return '<div class="bpile'+(n?'':' bempty')+'" onclick="bView(\''+k+'\')"><div class=bpcount>'+label+' &middot; '+n+'</div><div class=bptop>'+top+'</div></div>';}
function boardToolbar(){var it=selInst();if(!it)return '';var c=BY[it.id],onField=isSlot(sel.k);
  var h='<div class=btoolbar><span class=btsel>'+esc(c?c.n:'')+(it.fd?' &middot; face-down':'')+(it.def?' &middot; DEF':'')+'</span><span class=btsep></span>'
    +'<span class=mut style="font-size:11px">place as</span>'
    +'<button class="'+(placeMode==='atk'?'bon':'')+'" onclick="setPlace(\'atk\')">ATK</button>'
    +'<button class="'+(placeMode==='def'?'bon':'')+'" onclick="setPlace(\'def\')">DEF</button>'
    +'<button class="'+(placeMode==='set'?'bon':'')+'" onclick="setPlace(\'set\')">Set</button>'
    +'<span class=mut style="font-size:11px">&rarr; then tap a zone</span><span class=btsep></span>';
  if(onField)h+='<button onclick="bFlip()">Flip</button><button onclick="bRot()">ATK/DEF</button><span class=btsep></span>';
  h+='<button onclick="place(\'hand\')">Hand</button><button onclick="place(\'gy\')">GY</button><button onclick="place(\'ban\')">Banish</button>'
    +'<button onclick="place(\'deckTop\')">Deck top</button><button onclick="place(\'deckBtm\')">Deck btm</button>'
    +'<button onclick="place(\'ex\')">Extra</button>'
    +'<span class=btsep></span><button onclick="place(\'off\')" title="remove from play">&times; off</button>'
    +'<button onclick="sel=null;renderSim()">Cancel</button></div>';
  return h;}
function handHTML(){var h='<div class=bhandwrap><div class=bhlab>Hand &middot; '+board.hand.length+'</div><div class=bhcards>';
  h+=board.hand.map(function(it,i){return '<div onclick="bSelect(\'hand\',null,'+i+')">'+bCardHTML(it,sel&&sel.k==='hand'&&sel.i===i,false)+'</div>';}).join('');
  return h+'</div></div>';}
function viewerHTML(){if(!viewer)return '';var k=viewer,title,arr;
  if(k==='deck'){title='Deck ('+board.deck.length+')';arr=board.deck.map(function(id,i){return {id:id,i:i};});}
  else if(k==='ex'){title='Extra Deck ('+board.ex.length+')';arr=board.ex.map(function(id,i){return {id:id,i:i};});}
  else{title=(k==='gy'?'Graveyard':'Banished')+' ('+board[k].length+')';arr=board[k].map(function(it,i){return {id:it.id,i:i};});}
  var cards=arr.map(function(o){var c=BY[o.id];
    return '<div class=bvcard onclick="bSelect(\''+k+'\',null,'+o.i+')"><img src="data/images/'+o.id+'.jpg" onerror="this.style.display=\'none\';this.parentNode.classList.add(\'bnoart\')"><span class=bnm>'+esc(c?c.n:'')+'</span></div>';}).join('');
  return '<div class=bviewer onclick="bView(\''+k+'\')"><div class=bvbox onclick="event.stopPropagation()">'
    +'<div class=bvhead><b>'+title+'</b>'+(k==='deck'?' <span class=mut style="font-size:11px">order hidden &mdash; pick any card to act on it</span>':'')+'<button onclick="bView(\''+k+'\')" style="margin-left:auto">Close</button></div>'
    +'<div class=bvcards>'+(cards||'<span class=mut>Empty.</span>')+'</div></div></div>';}
function renderBoard(toggle){var h=toggle,decks=Object.keys(St.decks);
  h+='<div class=bctrl><label class=mut>Deck <select onchange="simDeck=this.value;boardNew()">'+decks.map(function(nm){return '<option'+(nm===simName()?' selected':'')+'>'+esc(nm)+'</option>';}).join('')+'</select></label>'
    +'<button onclick="boardNew()">&#8635; New game</button>';
  if(board)h+='<button onclick="bDraw(1)">Draw</button><button onclick="bDraw(5)">Open 5</button><button onclick="bDraw(6)">Open 6</button>'
    +'<span class=btsep></span><button onclick="bMillTop()">Mill top</button><button onclick="bBanishTop()">Banish top</button><button onclick="bShuffle()">&#128256; Shuffle</button>';
  h+='</div>';
  if(!board){h+='<div class=ins style="margin-top:12px">Pick a deck and press <b>New game</b>. Then <b>tap the Deck</b> to draw or search it, <b>tap a hand card</b> then a field zone to summon or set, and <b>tap any pile</b> (GY, Banished, Extra) to open it and act on the cards inside &mdash; the way DuelingBook works.</div>';document.getElementById('simBody').innerHTML=h;return;}
  h+=boardToolbar();
  if(!sel)h+='<div class=bhint>Tap a card to pick it up, then tap a zone to place it (ATK/DEF/Set chosen in the toolbar). Tap a pile to view and act on its cards.</div>';
  h+='<div class=bfield>';
  h+='<div class=bemzrow>'+slotHTML('emz',0,'EMZ')+slotHTML('emz',1,'EMZ')+'</div>';
  h+='<div class=bmainrow><div class=bside>'+slotHTML('fs',0,'Field')+'</div><div class=bzones>'+[0,1,2,3,4].map(function(s){return slotHTML('mon',s,'M'+(s+1));}).join('')+'</div><div class=bside>'+pileHTML('gy','GY')+'</div></div>';
  h+='<div class=bmainrow><div class=bside>'+pileHTML('ex','Extra')+'</div><div class=bzones>'+[0,1,2,3,4].map(function(s){return slotHTML('st',s,'S'+(s+1));}).join('')+'</div><div class=bside>'+pileHTML('deck','Deck')+'</div></div>';
  h+='<div class=bbanrow>'+pileHTML('ban','Banished')+'</div>';
  h+='</div>';
  h+=handHTML();
  h+=viewerHTML();
  document.getElementById('simBody').innerHTML=h;}

/* ===== Match log & win-rate analytics ===== */
var EVENTS=['Locals','Regional','YCS / Major','Online','Testing','Other'];
var lfDeck='all',lfOpp='all',lgEditId=null;
function parseImpact(str){if(!str)return [];return str.split(',').map(function(t){t=t.trim();if(!t)return null;var s=1;if(t.charAt(0)==='-'){s=-1;t=t.slice(1).trim();}else if(t.charAt(0)==='+'){t=t.slice(1).trim();}return t?{c:t,s:s}:null;}).filter(Boolean);}
function impactStr(a){return (a||[]).map(function(it){return (it.s<0?'-':'+')+it.c;}).join(', ');}
function logEditing(){return lgEditId!=null?St.log.filter(function(m){return m.id===lgEditId;})[0]:null;}
function logEdit(id){lgEditId=id;bkOpen.ladd=true;renderLog();}
function logCancelEdit(){lgEditId=null;renderLog();}
function logDel(id){St.log=St.log.filter(function(m){return m.id!==id;});if(lgEditId===id)lgEditId=null;sv();renderLog();}
function logSubmit(){var opp=document.getElementById('lgOpp').value.trim();
  var rec={date:document.getElementById('lgDate').value||new Date().toISOString().slice(0,10),event:document.getElementById('lgEvent').value,deck:document.getElementById('lgDeck').value||'Unspecified',opp:opp||'Unknown',res:document.getElementById('lgRes').value,play:document.getElementById('lgPlay').value,gw:parseInt(document.getElementById('lgGW').value,10)||0,gl:parseInt(document.getElementById('lgGL').value,10)||0,note:document.getElementById('lgNote').value.trim(),impact:parseImpact(document.getElementById('lgImpact').value)};
  if(lgEditId!=null){var m=logEditing();if(m)for(var k in rec)m[k]=rec[k];lgEditId=null;}else{rec.id=Date.now();St.log.push(rec);}
  sv();renderLog();}
function wrp(w,l){return (w+l)?w/(w+l):0;}
function logGroup(ms,kf){var g={};ms.forEach(function(m){var k=kf(m)||'—';g[k]=g[k]||{w:0,l:0,t:0};if(m.res==='W')g[k].w++;else if(m.res==='L')g[k].l++;else g[k].t++;});return g;}
function wrBars(g,minN){var rows=Object.keys(g).map(function(k){var s=g[k];return {k:k,w:s.w,l:s.l,t:s.t,n:s.w+s.l+s.t};}).filter(function(r){return r.n>=(minN||1);}).sort(function(a,b){return b.n-a.n||wrp(b.w,b.l)-wrp(a.w,a.l);});
  if(!rows.length)return '<div class=empty style="padding:6px 2px">Not enough matches yet.</div>';
  return rows.map(function(r){var gg=r.w+r.l,p=gg?100*r.w/gg:0;
    return '<div class=wrrow><div class=wrlab title="'+esc(r.k)+'">'+esc(r.k)+'</div><div class=wrtrack><div class=wrwin style="width:'+p.toFixed(0)+'%"></div></div><div class=wrval>'+r.w+'–'+r.l+(r.t?'–'+r.t:'')+' <b>'+(gg?p.toFixed(0)+'%':'—')+'</b></div></div>';}).join('');}
function logForm(){var e=logEditing()||{},today=new Date().toISOString().slice(0,10);
  var deckOpts='<option value=""'+(!e.deck?' selected':'')+'>— my deck —</option>'+Object.keys(St.decks).map(function(nm){return '<option'+(e.deck===nm?' selected':'')+'>'+esc(nm)+'</option>';}).join('')+'<option'+(e.deck==='Other'?' selected':'')+'>Other</option>';
  var evOpts=EVENTS.map(function(x){return '<option'+((e.event||'Locals')===x?' selected':'')+'>'+x+'</option>';}).join('');
  var resOpts=[['W','Win'],['L','Loss'],['T','Tie']].map(function(r){return '<option value="'+r[0]+'"'+((e.res||'W')===r[0]?' selected':'')+'>'+r[1]+'</option>';}).join('');
  var pdOpts=[['first','Went 1st'],['second','Went 2nd']].map(function(r){return '<option value="'+r[0]+'"'+((e.play||'first')===r[0]?' selected':'')+'>'+r[1]+'</option>';}).join('');
  return '<div class=bform>'
    +'<input type=date id=lgDate value="'+(e.date||today)+'">'
    +'<select id=lgEvent title="event">'+evOpts+'</select>'
    +'<select id=lgDeck title="your deck">'+deckOpts+'</select>'
    +'<input type=text id=lgOpp placeholder="opponent deck" value="'+eatt(e.opp||'')+'" style="min-width:150px">'
    +'<select id=lgRes title="match result">'+resOpts+'</select>'
    +'<select id=lgPlay title="play / draw">'+pdOpts+'</select>'
    +'<span class=mut style="font-size:11px;display:inline-flex;align-items:center;gap:5px">games won–lost <input class=gnum type=text inputmode=numeric maxlength=2 id=lgGW value="'+(e.gw||'')+'" placeholder="W">–<input class=gnum type=text inputmode=numeric maxlength=2 id=lgGL value="'+(e.gl||'')+'" placeholder="L"></span>'
    +'<input type=text id=lgNote placeholder="note (optional)" value="'+eatt(e.note||'')+'" style="flex:1;min-width:110px">'
    +'<input type=text id=lgImpact placeholder="impact cards, e.g. +Ash, -Maxx" value="'+eatt(impactStr(e.impact))+'" title="cards that helped (+) or bricked (−) this match — powers the Card impact analysis" style="flex:1;min-width:150px;border-color:rgba(143,220,255,.35)">'
    +'<button onclick="logSubmit()">'+(lgEditId!=null?'Save changes':'+ Log match')+'</button>'
    +(lgEditId!=null?'<button onclick="logCancelEdit()">Cancel</button>':'')+'</div>';}
function renderLog(){var L=St.log,RED='#ff9aa8';
  var w=0,l=0,t=0,gw=0,gl=0;L.forEach(function(m){if(m.res==='W')w++;else if(m.res==='L')l++;else t++;gw+=m.gw||0;gl+=m.gl||0;});
  var mwr=wrp(w,l)*100,rec=w+'–'+l+(t?'–'+t:''),gwr=(gw+gl)?100*gw/(gw+gl):0;
  var recent=L.slice().sort(function(a,b){return a.date<b.date?-1:a.date>b.date?1:a.id-b.id;}).slice(-12);
  var pips=recent.map(function(m){var c=m.res==='W'?'var(--pos)':m.res==='L'?RED:'var(--mut)';return '<span class=pip style="background:'+c+'" title="'+m.date+' vs '+esc(m.opp)+' — '+m.res+'"></span>';}).join('');
  var h='<div class=deckstats style="display:flex;gap:26px;flex-wrap:wrap;align-items:center">'
    +'<div><div class=mut style="font-size:11px">MATCH RECORD</div><div style="font-size:23px;font-weight:700">'+rec+'</div></div>'
    +'<div><div class=mut style="font-size:11px">WIN RATE</div><div style="font-size:23px;font-weight:700;color:'+(mwr>=50?'var(--pos)':RED)+'">'+((w+l)?mwr.toFixed(1)+'%':'—')+'</div></div>'
    +'<div><div class=mut style="font-size:11px">GAME RECORD</div><div style="font-size:16px;font-weight:700">'+((gw+gl)?gw+'–'+gl+' <span class=mut style="font-size:12px">('+gwr.toFixed(0)+'%)</span>':'<span class=mut style="font-size:13px">— add game scores</span>')+'</div></div>'
    +(recent.length?'<div style="margin-left:auto"><div class=mut style="font-size:11px;text-align:right">RECENT FORM</div><div class=pips>'+pips+'</div></div>':'')+'</div>';
  h+=grp('ladd',lgEditId!=null?'Edit match':'Log a match',null,logForm());
  // filters + history
  var decks=Array.from(new Set(L.map(function(m){return m.deck;}))),opps=Array.from(new Set(L.map(function(m){return m.opp;})));
  var fm=L.filter(function(m){return (lfDeck==='all'||m.deck===lfDeck)&&(lfOpp==='all'||m.opp===lfOpp);}).sort(function(a,b){return a.date<b.date?1:a.date>b.date?-1:b.id-a.id;});
  var lb='<div class=bform>'
    +'<label class=mut>Deck <select onchange="lfDeck=this.value;renderLog()"><option value=all'+(lfDeck==='all'?' selected':'')+'>all</option>'+decks.map(function(d){return '<option'+(lfDeck===d?' selected':'')+'>'+esc(d)+'</option>';}).join('')+'</select></label>'
    +'<label class=mut>Opponent <select onchange="lfOpp=this.value;renderLog()"><option value=all'+(lfOpp==='all'?' selected':'')+'>all</option>'+opps.map(function(o){return '<option'+(lfOpp===o?' selected':'')+'>'+esc(o)+'</option>';}).join('')+'</select></label></div>';
  if(!fm.length)lb+='<div class=empty>'+(L.length?'No matches match the filter.':'No matches logged yet — record one above after your next locals.')+'</div>';
  else lb+='<div style="overflow-x:auto"><table><tr><th>Date</th><th>Event</th><th>My deck</th><th>Opponent</th><th>Result</th><th>P/D</th><th>Games</th><th>Note</th><th></th></tr>'+fm.map(function(m){var rc=m.res==='W'?'var(--pos)':m.res==='L'?RED:'var(--mut)',rl=m.res==='W'?'Win':m.res==='L'?'Loss':'Tie';
    return '<tr><td>'+m.date+'</td><td class=mut>'+esc(m.event||'')+'</td><td>'+esc(m.deck||'')+'</td><td>'+esc(m.opp||'')+'</td><td style="color:'+rc+';font-weight:700">'+rl+'</td><td class=mut>'+(m.play==='second'?'2nd':'1st')+'</td><td class=mut>'+((m.gw||m.gl)?m.gw+'–'+m.gl:'—')+'</td><td class=mut style="max-width:160px;overflow:hidden;text-overflow:ellipsis">'+esc(m.note||'')+'</td><td style="white-space:nowrap"><span class=addb onclick="logEdit('+m.id+')" title="edit">✎</span><span class=x onclick="logDel('+m.id+')" title="delete">✕</span></td></tr>';}).join('')+'</table></div>';
  h+=grp('lhist','Match history',L.length?fm.length+' of '+L.length:null,lb);
  // by deck
  h+=grp('ldeck','Win rate by deck',null,L.length?wrBars(logGroup(fm,function(m){return m.deck;})):'<div class=empty>Log matches to see this.</div>');
  // by matchup
  h+=grp('lmatch','Win rate by matchup',null,L.length?wrBars(logGroup(fm,function(m){return m.opp;})):'<div class=empty>Log matches to see this.</div>');
  // card impact
  var impMap={};fm.forEach(function(m){(m.impact||[]).forEach(function(it){var k=it.c;impMap[k]=impMap[k]||{h:{w:0,l:0,t:0},x:{w:0,l:0,t:0}};var bk=it.s<0?impMap[k].x:impMap[k].h;if(m.res==='W')bk.w++;else if(m.res==='L')bk.l++;else bk.t++;});});
  var impRows=Object.keys(impMap).map(function(k){var o=impMap[k];return {k:k,h:o.h,x:o.x,n:o.h.w+o.h.l+o.h.t+o.x.w+o.x.l+o.x.t};}).sort(function(a,b){return b.n-a.n;});
  var ovWr=wrp(w,l);
  var impBody;
  if(!impRows.length)impBody='<div class=ins>Testing a card? When you log a match, add it to <b>impact cards</b> with <b>+</b> (it carried the game) or <b>−</b> (it bricked). This section then shows your win rate in the matches where you flagged it — a quick read on whether a card you’re debating is pulling its weight. <span class=mut>Small samples are noisy, so treat it as a nudge, not proof.</span></div>';
  else impBody=impRows.map(function(r){var hg=r.h.w+r.h.l,xg=r.x.w+r.x.l,delta=(hg&&(w+l))?(r.h.w/hg-ovWr)*100:null;
    return '<div class=improw><div class=impnm title="'+esc(r.k)+'">'+esc(r.k)+'</div><div class=impstat>'
      +(hg?'<b style="color:var(--pos)">carried</b> '+r.h.w+'–'+r.h.l+(r.h.t?'–'+r.h.t:'')+' <b>'+Math.round(100*r.h.w/hg)+'%</b>'+(delta!=null?' <span style="color:'+(delta>=0?'var(--pos)':RED)+'">('+(delta>=0?'+':'')+delta.toFixed(0)+' vs overall)</span>':''):'<span class=mut>no + games yet</span>')
      +(xg?' · <b style="color:'+RED+'">bricked</b> '+r.x.w+'–'+r.x.l+(r.x.t?'–'+r.x.t:''):'')+'</div></div>';}).join('')
    +'<div class=mut style="font-size:11px;margin-top:8px;max-width:648px">“Carried” = matches you flagged the card <b>+</b>; the % is your win rate in just those, compared to your overall <b>'+((w+l)?(ovWr*100).toFixed(0)+'%':'—')+'</b>. It’s your own per-game judgment, not automatic — and with few games it swings hard, so use it to spot a trend, not to settle a debate.</div>';
  h+=grp('limpact','Card impact — is it pulling its weight?',impRows.length?impRows.length+' tracked':null,impBody);
  // splits
  var splitBody;
  if(!fm.length)splitBody='<div class=empty>Log matches to see splits.</div>';
  else{var byPD=logGroup(fm,function(m){return m.play==='second'?'On the draw (2nd)':'On the play (1st)';});
    var pf=byPD['On the play (1st)']||{w:0,l:0,t:0},pd=byPD['On the draw (2nd)']||{w:0,l:0,t:0};
    var pfw=wrp(pf.w,pf.l)*100,pdw=wrp(pd.w,pd.l)*100;
    splitBody='<div class=chlab>Play vs draw</div>'+wrBars(byPD)
      +'<div class=chlab style="margin-top:14px">By event</div>'+wrBars(logGroup(fm,function(m){return m.event||'—';}))
      +'<div class=trend style="margin-top:12px">Overall you win <b>'+((w+l)?mwr.toFixed(0):'—')+'%</b> of matches ('+rec+'). '
      +((pf.w+pf.l)&&(pd.w+pd.l)?'On the play you win <b style="color:'+(pfw>=pdw?'var(--pos)':RED)+'">'+pfw.toFixed(0)+'%</b> vs <b style="color:'+(pdw>=pfw?'var(--pos)':RED)+'">'+pdw.toFixed(0)+'%</b> on the draw — the sim assumes 5 cards on the play, 6 on the draw, so this is the real-world payoff of that extra card.':'Log which games you went first vs second to unlock the play/draw split (the real-world counterpart to the simulator).')+'</div>';}
  h+=grp('lsplit','Splits &amp; trends',null,splitBody);
  document.getElementById('plogBody').innerHTML=h;}

/* ===== Sets browser ===== */
var setView=null;
function openSet(i){setView=i;renderSets();}
function backSets(){setView=null;renderSets();}
function setAgg(s){var seen={},ms=[],rc={},tot=0,dates=[];
  s.k.forEach(function(p){var c=BY[p[0]];if(!c)return;var rn=RAR[p[1]]||'—';rc[rn]=(rc[rn]||0)+1;
    if(!seen[p[0]]){seen[p[0]]=1;if(c.m!=null){ms.push(c.m);tot+=c.m;}if(c.rd)dates.push(c.rd);}});
  ms.sort(function(a,b){return a-b;});
  var ds=dates.slice().sort();
  return {cards:Object.keys(seen).length,printings:s.k.length,priced:ms.length,
    med:ms.length?ms[Math.floor(ms.length/2)]:null,tot:tot,rc:rc,
    max:ms.length?ms[ms.length-1]:null,date:ds.length?ds[ds.length-1]:null};}
function renderSets(){
  if(setView!=null){renderSetDetail(setView);return;}
  setsBody.innerHTML='<div class=bar style="margin:2px 0 10px"><input type=text id=setq placeholder="search '+SETS.length.toLocaleString()+' sets…" oninput="fSets()" style="width:230px">'
    +'<label class=mut>Sort <select id=setsort onchange="fSets()"><option value=cards>Most cards</option><option value=value>Total value</option><option value=name>Name A–Z</option><option value=date>Newest</option></select></label></div><div id=setList></div>';
  fSets();}
function fSets(){var q=(document.getElementById('setq')?document.getElementById('setq').value:'').toLowerCase();
  var sr=document.getElementById('setsort')?document.getElementById('setsort').value:'cards';
  var rows=SETS.map(function(s,i){return {i:i,s:s,a:null};}).filter(function(o){return !q||o.s.n.toLowerCase().indexOf(q)>=0||(o.s.c||'').toLowerCase().indexOf(q)>=0;});
  rows.forEach(function(o){o.a=setAgg(o.s);});
  rows.sort(function(x,y){if(sr==='name')return x.s.n<y.s.n?-1:x.s.n>y.s.n?1:0;
    if(sr==='value')return y.a.tot-x.a.tot;if(sr==='date')return (y.a.date||'')<(x.a.date||'')?-1:(y.a.date||'')>(x.a.date||'')?1:0;
    return y.a.cards-x.a.cards;});
  var shown=rows.slice(0,400);
  document.getElementById('setList').innerHTML='<div class=count>'+rows.length+' sets'+(rows.length>400?' · showing top 400':'')+'</div>'
    +'<table><tr><th>Set</th><th>Code</th><th class=r>Cards</th><th class=r>Total value</th><th>Newest card</th></tr>'
    +shown.map(function(o){return '<tr class=setrow onclick="openSet('+o.i+')"><td class=nm>'+esc(o.s.n)+'</td><td class=mut>'+esc(o.s.c||'')+'</td><td class="r">'+o.a.cards+'</td><td class="r">'+f(o.a.tot||null)+'</td><td class=mut>'+(o.a.date?fdate(o.a.date):'—')+'</td></tr>';}).join('')+'</table>';}
function renderSetDetail(i){var s=SETS[i];if(!s){setView=null;renderSets();return;}var a=setAgg(s);
  var h='<div class=bar style="margin-bottom:8px"><button onclick="backSets()">← All sets</button></div>';
  h+='<div class=deckstats><b style="font-size:16px">'+esc(s.n)+'</b>'+(s.c?' <span class=mut>('+esc(s.c)+')</span>':'')+(a.date?' · <span class=mut>newest card '+fdate(a.date)+'</span>':'')+'</div>';
  h+='<div class=ovw style="margin:10px 0">'+ost(a.cards,'cards')+ost(a.printings,'printings')+ost(f(a.med),'median price')+ost(f(a.tot),'total value')+ost(a.max!=null?'$'+a.max.toFixed(2):'—','priciest')+'</div>';
  var rr=Object.keys(a.rc).map(function(k){return {k:k,v:a.rc[k]};}).sort(function(x,y){return (ORD[x.k]||0)-(ORD[y.k]||0);});
  var mx=Math.max.apply(0,rr.map(function(r){return r.v;}))||1;
  h+='<h2 class=sec>Rarity distribution</h2>'+rr.map(function(r){return '<div class=crow><div class="clab '+rarClass(r.k)+'">'+esc(r.k)+'</div><div class=cbarwrap><div class=cbar style="width:'+(100*r.v/mx).toFixed(1)+'%"></div></div><div class=cval>'+r.v+' card'+(r.v===1?'':'s')+'</div></div>';}).join('');
  var byCard={};s.k.forEach(function(p){(byCard[p[0]]=byCard[p[0]]||[]).push(p[1]);});
  var cs=Object.keys(byCard).map(function(id){id=+id;var rs=byCard[id].slice().sort(function(x,y){return y-x;}).map(function(ix){return RAR[ix]||'—';});return {id:id,rs:rs,m:BY[id]?BY[id].m:null};});
  cs.sort(function(x,y){return (y.m==null?-1:y.m)-(x.m==null?-1:x.m);});
  h+='<h2 class=sec>Cards ('+cs.length+')</h2><div style="overflow-x:auto"><table><tr><th>Card</th><th>Rarities in set</th><th class=r>Market low</th></tr>'
    +cs.map(function(o){var c=BY[o.id];return '<tr><td class=nm onclick="openM('+o.id+')">'+esc(c?c.n:''+o.id)+'</td><td>'+o.rs.map(function(rn){return '<span class="'+rarClass(rn)+'">'+esc(rn)+'</span>';}).join(', ')+'</td><td class="r">'+f(o.m)+'</td></tr>';}).join('')+'</table></div>';
  if(St.meta&&St.meta.length){var mf=metaFreq();var ms=cs.filter(function(o){return mf[o.id];}).sort(function(x,y){return mf[y.id]-mf[x.id];});
    if(ms.length)h+='<h2 class=sec>Meta cards in this set</h2>'+ms.map(function(o){var c=BY[o.id];return '<div class=crow><div class=clab style="text-align:left;width:auto;min-width:180px">'+esc(c?c.n:'')+'</div><div class=mut style="font-size:11px">in '+mf[o.id]+'/'+St.meta.length+' of your meta decks · '+o.rs.join(', ')+' · '+f(o.m)+'</div></div>';}).join('');
    else h+='<div class=mut style="font-size:11px;margin-top:10px">No cards from this set appear in your tracked meta decks.</div>';}
  else h+='<div class=mut style="font-size:11px;margin-top:10px;max-width:648px">Price stats use each card’s market low (cheapest copy, any printing). Import decks in the <b>Meta</b> tab and this set will show which of its cards are meta staples.</div>';
  setsBody.innerHTML=h;}

/* ===== Meta: curate top decks -> staples & gaps ===== */
var TIERS=['Tier 0','Tier 1','Tier 2','Rogue','Casual','Testing'];
function metaFreq(){var f={};St.meta.forEach(function(d){for(var id in d.cnt)f[id]=(f[id]||0)+1;});return f;}
function ydkToCnt(txt){var s=parseYdk(txt),cnt={};['main','extra','side'].forEach(function(sec){for(var id in s[sec])cnt[id]=(cnt[id]||0)+s[sec][id];});
  if(!Object.keys(cnt).length){var t=parseTextList(txt);for(var id in t)if(BY[id])cnt[id]=t[id];}   // fall back to name/text list
  return cnt;}
function metaImport(ev){var fls=Array.prototype.slice.call(ev.target.files||[]);if(!fls.length)return;var done=0,added=0,skip=0;
  fls.forEach(function(fl){var rd=new FileReader();
    rd.onload=function(){var cnt=ydkToCnt(rd.result);
      if(Object.keys(cnt).length){St.meta.push({id:Date.now()+added,name:fl.name.replace(/\.(ydk|txt)$/i,'')||'Imported deck',tier:'Tier 1',cnt:cnt});added++;}else skip++;
      if(++done===fls.length){sv();renderMeta();if(skip)alert(skip+' file(s) had no recognizable cards and were skipped.');}};
    rd.readAsText(fl);});
  ev.target.value='';}
function metaPaste(){var el=document.getElementById('mpTxt');if(!el)return;var cnt=ydkToCnt(el.value);
  if(!Object.keys(cnt).length){alert('No recognizable cards — paste a .ydk (card IDs) or a "3x Card Name" list.');return;}
  var nm=(document.getElementById('mpNm').value||'').trim()||'Pasted deck';
  St.meta.push({id:Date.now(),name:nm,tier:document.getElementById('mpTier').value||'Tier 1',cnt:cnt});sv();renderMeta();}
function metaRename(id){var d=St.meta.filter(function(x){return x.id===id;})[0];if(!d)return;var nm=(prompt('Rename deck:',d.name)||'').trim();if(nm){d.name=nm;sv();renderMeta();}}
function metaSetTier(id,t){var d=St.meta.filter(function(x){return x.id===id;})[0];if(d){d.tier=t;sv();renderMeta();}}
function metaDel(id){St.meta=St.meta.filter(function(d){return d.id!==id;});sv();renderMeta();}
function renderMeta(){var M=St.meta,RED='#ff9aa8';
  var freq={},cop={};M.forEach(function(d){for(var id in d.cnt){freq[id]=(freq[id]||0)+1;cop[id]=(cop[id]||0)+d.cnt[id];}});
  var staples=Object.keys(freq).map(function(id){return {id:+id,f:freq[id],avg:cop[id]/freq[id]};}).sort(function(a,b){return b.f-a.f||b.avg-a.avg||((BY[b.id]?BY[b.id].m:0)-(BY[a.id]?BY[a.id].m:0));});
  var owned=function(id){return ownQ(id);};
  var missing=staples.filter(function(s){return owned(s.id)<Math.round(s.avg);});
  var missCost=missing.reduce(function(t,s){var c=BY[s.id];var need=Math.round(s.avg)-owned(s.id);return t+((c&&c.m!=null)?c.m*Math.max(0,need):0);},0);
  var h='<div class=deckstats style="display:flex;gap:26px;flex-wrap:wrap;align-items:center">'
    +'<div><div class=mut style="font-size:11px">META DECKS</div><div style="font-size:22px;font-weight:700">'+M.length+'</div></div>'
    +'<div><div class=mut style="font-size:11px">STAPLES TRACKED</div><div style="font-size:22px;font-weight:700">'+staples.length+'</div></div>'
    +'<div><div class=mut style="font-size:11px">STAPLES YOU’RE MISSING</div><div style="font-size:22px;font-weight:700;color:'+(missing.length?'var(--warn)':'var(--pos)')+'">'+missing.length+'</div></div>'
    +'<div><div class=mut style="font-size:11px">COST TO CLOSE GAPS</div><div style="font-size:22px;font-weight:700">$'+missCost.toFixed(2)+'</div></div></div>';
  var imp='<div class=bar style="margin-bottom:6px"><button onclick="document.getElementById(\'metaFile\').click()">＋ Import .ydk — pick several at once</button></div>'
    +'<details class=mpaste><summary>or paste a decklist</summary><div class=bform style="margin-top:8px">'
    +'<input type=text id=mpNm placeholder="deck name" style="min-width:170px">'
    +'<select id=mpTier>'+TIERS.map(function(t){return '<option'+(t==='Tier 1'?' selected':'')+'>'+t+'</option>';}).join('')+'</select>'
    +'<button onclick="metaPaste()">Add deck</button></div>'
    +'<textarea id=mpTxt placeholder="paste a .ydk (card IDs) — or a list like:  3x Ash Blossom &amp; Joyous Spring"></textarea></details>';
  if(!M.length)imp+='<div class=ins style="margin-top:8px">Export current top decks as <code>.ydk</code> (from YGOPRODeck, your sim, wherever you read the meta) and drop them in — you can select many files at once. Tag a tier, and CYBERSE finds the <b>staples</b> shared across them and flags which ones you’re <b>missing</b> — priced, one click onto your wishlist. You curate the decks; nothing is scraped.</div>';
  else imp+='<div style="overflow-x:auto;margin-top:10px"><table><tr><th>Deck</th><th>Tier</th><th class=r>Cards</th><th class=r>Value</th><th class=r>Cost to you</th><th></th></tr>'+M.map(function(d){
    var val=0,toyou=0;for(var id in d.cnt){var c=BY[id];if(!c||c.m==null)continue;val+=c.m*d.cnt[id];toyou+=c.m*Math.max(0,d.cnt[id]-owned(id));}
    return '<tr><td class=nm onclick="metaRename('+d.id+')" title="click to rename">'+esc(d.name)+'</td><td><select onchange="metaSetTier('+d.id+',this.value)" style="font-size:11px">'+TIERS.map(function(t){return '<option'+((d.tier||'Tier 1')===t?' selected':'')+'>'+t+'</option>';}).join('')+'</select></td><td class=r>'+Object.keys(d.cnt).length+'</td><td class="r">$'+val.toFixed(2)+'</td><td class="r">$'+toyou.toFixed(2)+'</td><td class=x onclick="metaDel('+d.id+')" title="remove">✕</td></tr>';}).join('')+'</table></div>';
  h+=grp('mdecks','Meta decks',M.length?M.length+' imported':null,imp);
  var stBody=!staples.length?'<div class=empty>Import a couple of meta decks to surface staples.</div>'
    :'<table><tr><th>Card</th><th class=r>In decks</th><th class=r>Typical</th><th class=r>Market low</th><th class=r>You own</th></tr>'+staples.slice(0,80).map(function(s){var c=BY[s.id],own=owned(s.id),need=Math.round(s.avg);
      return '<tr><td class=nm onclick="openM('+s.id+')">'+esc(c?c.n:''+s.id)+'</td><td class=r>'+s.f+'/'+M.length+'</td><td class=r>'+need+'×</td><td class="r">'+f(c?c.m:null)+'</td><td class="r" style="color:'+(own>=need?'var(--pos)':own>0?'var(--warn)':RED)+'">'+own+'</td></tr>';}).join('')+'</table>';
  h+=grp('mstaples','Staples across your meta decks',staples.length?staples.length+' cards':null,stBody);
  var gapBody;
  if(!M.length)gapBody='<div class=empty>Import meta decks first.</div>';
  else if(!missing.length)gapBody='<div class=ins style="border-left-color:var(--pos)">You already own every staple in your tracked meta decks. Nicely positioned.</div>';
  else gapBody='<div style="overflow-x:auto"><table><tr><th>Missing staple</th><th class=r>In decks</th><th class=r>Need</th><th class=r>Unit</th><th class=r>Cost</th><th></th></tr>'+missing.map(function(s){var c=BY[s.id],need=Math.round(s.avg)-owned(s.id);
      return '<tr><td class=nm onclick="openM('+s.id+')">'+esc(c?c.n:''+s.id)+'</td><td class=r>'+s.f+'/'+M.length+'</td><td class=r>'+need+'</td><td class="r">'+f(c?c.m:null)+'</td><td class="r">'+f((c&&c.m!=null)?c.m*need:null)+'</td><td style="white-space:nowrap"><span class=addb onclick="add(\'wishlist\','+s.id+')" title="add to wishlist">+Wish</span></td></tr>';}).join('')+'</table></div>'
      +'<div class=mut style="font-size:11px;margin-top:6px">Ranked by how many of your meta decks run each card. Total to close every gap: <b>$'+missCost.toFixed(2)+'</b>.</div>';
  h+=grp('mgaps','Your gaps — staples you’re missing',missing.length?missing.length+' missing':null,gapBody);
  metaBody.innerHTML=h;}

function rarPrice(c,rs){return rs===''?(c.hr?c.rp[c.hr]:null):(rs in c.rp?c.rp[rs]:null);}
function rB(){
  var q=q_.value.toLowerCase(),qa=qa_.value.toLowerCase(),rs=rar_.value,cl=cl_.value,bn=bn_.value;
  var pmin=numv(pmin_.value),pmax=numv(pmax_.value),dl=deal_.checked;
  document.getElementById('ph').textContent=(rs===''?'Top-rarity':rs)+' $';
  var v=[];
  for(var i=0;i<CARDS.length;i++){var c=CARDS[i];
    if(q&&c.n.toLowerCase().indexOf(q)<0)continue;
    if(qa&&c.ar.toLowerCase().indexOf(qa)<0)continue;
    if(cl&&c.cl!==cl)continue; if(bn&&c.bn!==bn)continue;
    if(rs!==''&&!(rs in c.rp))continue;
    var act=rs===''?c.m:rarPrice(c,rs);
    if(pmin!=null&&(act==null||act<pmin))continue;
    if(pmax!=null&&(act==null||act>pmax))continue;
    if(dl&&!c.deal)continue;
    v.push({c:c,rp:rarPrice(c,rs)});
  }
  var ow=function(c){return ownQ(c.i);};
  v.sort(function(a,b){var x=sk==='m'?a.c.m:sk==='rarity'?a.rp:sk==='own'?ow(a.c):a.c[sk], y=sk==='m'?b.c.m:sk==='rarity'?b.rp:sk==='own'?ow(b.c):b.c[sk];
    if(x==null)return 1; if(y==null)return -1; if(typeof x==='string')return x.localeCompare(y)*sd; return (x-y)*sd;});
  cnt_.textContent=v.length.toLocaleString()+' cards'+(v.length>LIMIT?' (first '+LIMIT+')':'');
  tb_.innerHTML=v.slice(0,LIMIT).map(function(o){var c=o.c;
    return '<tr><td class="nm" onclick="openM('+c.i+')">'+esc(c.n)+'</td><td>'+c.cl+'</td>'
    +'<td>'+(c.bn==='Unlimited'?'<span class=mut>—</span>':'<span class=pill>'+c.bn+'</span>')+'</td>'
    +'<td class="mut">'+esc(c.ar)+'</td><td class="'+rarClass(c.hr)+'">'+(c.hr||'')+'</td><td class="r mut">'+(c.ag==null?'':c.ag)+'</td>'
    +'<td class="r'+(ownQ(c.i)?' own':' mut')+'">'+(ownQ(c.i)||'·')+'</td>'
    +'<td class="r">'+f(c.m)+'</td><td class="r rar">'+f(o.rp)+'</td>'
    +'<td class="r '+(c.deal?'deal':'mut')+'">'+(c.gap==null?'':c.gap+'×')+'</td>'
    +'<td><span class=addb onclick="addToDeck('+c.i+')">+D</span><span class=addb onclick="add(\'collection\','+c.i+')">+C</span><span class=addb onclick="add(\'wishlist\','+c.i+')">+W</span></td></tr>';}).join('');
}
var listMode='list';
function setListMode(m){listMode=m;var a=document.getElementById('vtList'),b=document.getElementById('vtGrid');if(a)a.classList.toggle('on',m==='list');if(b)b.classList.toggle('on',m==='grid');if(view==='deck')renderDeck();else rTable();}
function gridTile(key,id,inDeck,li){var m=bucket(key),c=BY[id],e=inDeck?m[id]:(isMulti(key)?m[id][li]:m[id]),p=entPrice(e,c),feed=priceOf(c,e.rar);
  var L=inDeck?'':(','+li);
  var own=inDeck?ownQ(id):0, buy=inDeck?Math.max(0,e.q-own):e.q, unowned=inDeck&&buy>0;
  var addb=inDeck?'<span class=gab onclick="add(\'collection\','+id+')" title="add to collection">+C</span><span class=gab onclick="add(\'wishlist\','+id+')" title="add to wishlist">+W</span>'
    :(key==='collection')?'<span class=gab onclick="addLine(\'collection\','+id+')" title="add another version">+v</span><span class=gab onclick="addToDeck('+id+')" title="add to active deck">+D</span><span class=gab onclick="add(\'wishlist\','+id+')" title="add to wishlist">+W</span>'
    :(key==='wishlist')?'<span class=gab onclick="addLine(\'wishlist\','+id+')" title="add another version">+v</span><span class=gab onclick="addToDeck('+id+')" title="add to active deck">+D</span><span class=gab onclick="add(\'collection\','+id+')" title="add to collection">+C</span>':'';
  var raropts='<option value="__m"'+(e.rar==='__m'?' selected':'')+'>Mkt low</option>'+Object.keys(c.rp).map(function(rn){return '<option'+(e.rar===rn?' selected':'')+'>'+rn+'</option>';}).join('');
  var condsel=inDeck?'':'<select class=grar onchange="setCond(\''+key+'\','+id+',this.value'+L+')" title="condition">'+CONDS.map(function(x){return '<option value="'+x+'"'+((e.cond||'')===x?' selected':'')+'>'+(x||'cond')+'</option>';}).join('')+'</select>';
  var prsel=(key==='wishlist')?'<select class=grar onchange="setP('+id+',this.value'+L+')">'+['High','Normal','Low'].map(function(x){return '<option'+((e.pr||'Normal')===x?' selected':'')+'>'+x+'</option>';}).join('')+'</select>':'';
  var mv=inDeck?(key==='side'?'<span class=gab onclick="moveTo('+id+',\'side\',\''+deckSecOf(id)+'\')" title="to main/extra">→M</span>':'<span class=gab onclick="moveTo('+id+',\''+key+'\',\'side\')" title="to side deck">→S</span>'):'';
  return '<div class="gcard'+(unowned?' unowned':'')+'">'
    +'<div class=gimgwrap onclick="openM('+id+')"><img class=gimg src="data/images/'+id+'.jpg" onerror="this.style.display=\'none\';this.parentNode.classList.add(\'noart\')"><div class=gph>'+esc(c.n)+'</div>'
      +'<div class=gqty>×'+e.q+'</div>'+(unowned?'<div class=gneed title="you still need '+buy+'">◆'+buy+'</div>':'')+'</div>'
    +'<div class=gname onclick="openM('+id+')" title="'+eatt(c.n)+'">'+esc(c.n)+'</div>'
    +'<div class=gmeta>'+(inDeck?'<span>'+f(p)+'</span><span class=mut>own '+own+'</span>':'<input class="ovin'+(e.ov!=null?' ovset':'')+'" value="'+(e.ov!=null?e.ov:'')+'" placeholder="'+(feed!=null?feed.toFixed(2):'—')+'" onchange="setOv(\''+key+'\','+id+',this.value'+L+')" title="your price — blank uses the feed" onclick="event.stopPropagation()"><span class=mut>'+((e.cond||'')||(e.ov!=null?'yours':''))+'</span>')+'</div>'
    +'<div class=gact><span class=qbtn onclick="setQ(\''+key+'\','+id+',-1'+L+')">–</span><span class=gqn>'+e.q+'</span><span class=qbtn onclick="setQ(\''+key+'\','+id+',1'+L+')">+</span><span class=gsp></span>'+addb+'<span class=x onclick="del(\''+key+'\','+id+''+L+')">✕</span></div>'
    +'<div class=gact><select class=grar onchange="setR(\''+key+'\','+id+',this.value'+L+')">'+raropts+'</select>'+condsel+prsel+mv+'</div>'
    +'</div>';}
var CONDS=['','NM','LP','MP','HP','DMG'];
function listRow(key,id,inDeck,li){var m=bucket(key),c=BY[id],e=inDeck?m[id]:(isMulti(key)?m[id][li]:m[id]),p=entPrice(e,c),feed=priceOf(c,e.rar);
  var L=inDeck?'':(','+li);
  var opts='<option value="__m"'+(e.rar==='__m'?' selected':'')+'>Market low</option>'+
    Object.keys(c.rp).map(function(rn){return '<option'+(e.rar===rn?' selected':'')+'>'+rn+'</option>';}).join('');
  var own=inDeck?ownQ(id):0, buy=inDeck?Math.max(0,e.q-own):e.q;
  var unowned=inDeck&&buy>0;
  var pr=e.pr||'Normal';
  var prcell=(key==='wishlist')?'<td><select onchange="setP('+id+',this.value'+L+')" style="font-size:11px">'+['High','Normal','Low'].map(function(x){return '<option'+(pr===x?' selected':'')+'>'+x+'</option>';}).join('')+'</select></td>':'';
  var condcell=inDeck?'':'<td><select onchange="setCond(\''+key+'\','+id+',this.value'+L+')" style="font-size:11px">'+CONDS.map(function(x){return '<option value="'+x+'"'+((e.cond||'')===x?' selected':'')+'>'+(x||'—')+'</option>';}).join('')+'</select></td>';
  var extra=inDeck?'<span class=addb onclick="add(\'collection\','+id+')" title="add to collection">+Coll</span><span class=addb onclick="add(\'wishlist\','+id+')" title="add to wishlist">+Wish</span>'
    :(key==='collection')?'<span class=addb onclick="addLine(\'collection\','+id+')" title="add another rarity/version you own">+ver</span><span class=addb onclick="addToDeck('+id+')" title="add to active deck">+Deck</span><span class=addb onclick="add(\'wishlist\','+id+')" title="add to wishlist">+Wish</span>'
    :(key==='wishlist')?'<span class=addb onclick="addLine(\'wishlist\','+id+')" title="add another rarity/version">+ver</span><span class=addb onclick="addToDeck('+id+')" title="add to active deck">+Deck</span><span class=addb onclick="add(\'collection\','+id+')" title="add to collection">+Coll</span>':'';
  var mv=inDeck?(key==='side'?'<span class=addb onclick="moveTo('+id+',\'side\',\''+deckSecOf(id)+'\')" title="move to main/extra">→ main</span>':'<span class=addb onclick="moveTo('+id+',\''+key+'\',\'side\')" title="move to side deck">→ side</span>'):'';
  return '<tr'+(unowned?' class=unowned':'')+'><td class="nm" onclick="openM('+id+')">'+(unowned?'<span class=needdot title="you still need '+buy+'">◆</span>':'')+esc(c.n)+'</td>'
    +'<td><span class=qbtn onclick="setQ(\''+key+'\','+id+',-1'+L+')">–</span>'+e.q+'<span class=qbtn onclick="setQ(\''+key+'\','+id+',1'+L+')">+</span></td>'
    +prcell+(inDeck?'<td class="r mut">'+own+'</td><td class="r"'+(buy>0?' style="color:var(--warn);font-weight:700"':'')+'>'+buy+'</td>':'')
    +'<td><select onchange="setR(\''+key+'\','+id+',this.value'+L+')" style="font-size:11px">'+opts+'</select></td>'
    +condcell
    +(inDeck?'<td class="r">'+f(p)+'</td>':'<td class="r"><input class="ovin'+(e.ov!=null?' ovset':'')+'" value="'+(e.ov!=null?e.ov:'')+'" placeholder="'+(feed!=null?feed.toFixed(2):'—')+'" onchange="setOv(\''+key+'\','+id+',this.value'+L+')" title="your price — blank uses the feed price"></td>')
    +'<td class="r">'+f(p==null?null:p*(inDeck?buy:e.q))+'</td>'
    +'<td>'+extra+mv+' <span class=x onclick="del(\''+key+'\','+id+''+L+')">✕</span></td></tr>';}
function secTable(sec,label,lim,lq){var m=curDeck()[sec];var cnt=0;Object.keys(m).forEach(function(id){cnt+=m[id].q;});
  var ids=Object.keys(m).filter(function(id){var c=BY[id];return c&&(!lq||c.n.toLowerCase().indexOf(lq)>=0);});
  var over=(lim&&cnt>lim)?' <span style="color:#e0607a">(max '+lim+')</span>':'';
  var head='<h3 class=sec>'+label+' — '+cnt+' card'+(cnt===1?'':'s')+over+'</h3>';
  if(!Object.keys(m).length)return head+'<div class=empty style="padding:4px 2px">empty</div>';
  if(listMode==='grid')return head+(ids.length?'<div class=grid>'+ids.map(function(id){return gridTile(sec,id,true);}).join('')+'</div>':'<div class=empty style="padding:4px 2px">no matches</div>');
  var rows=ids.map(function(id){return listRow(sec,id,true);}).join('');
  return head+'<table><tr><th>Card</th><th>Qty</th><th class=r>Own</th><th class=r>Buy</th><th>Rarity (which you own)</th><th class=r>Unit</th><th class=r>To-buy</th><th></th></tr>'+rows+'</table>';}
function renderDeck(){var d=curDeck(),lqel=document.getElementById('lq'),lq=lqel?lqel.value.toLowerCase():'';
  var need={};['main','extra','side'].forEach(function(sec){for(var id in d[sec])need[id]=(need[id]||0)+d[sec][id].q;});
  var viol=[];for(var id in need){var c=BY[id];if(!c)continue;var al={Forbidden:0,Limited:1,'Semi-Limited':2}[c.bn];if(al===undefined)al=3;if(need[id]>al)viol.push(esc(c.n)+' ('+need[id]+'/'+al+')');}
  var mainCt=0;for(var mid in d.main)mainCt+=d.main[mid].q;
  var legal=viol.length?'<span style="color:#e0607a">⚠ '+viol.length+' over banlist limit — '+viol.join(', ')+'</span>':'<span style="color:var(--pos)">✓ banlist-legal</span>';
  var mw=(mainCt<40||mainCt>60)?' <span style="color:'+(mainCt<40?'var(--warn)':'#e0607a')+'">(main 40–60)</span>':'';
  var ownTot=0,needTot=0;for(var nid in need){needTot+=need[nid];var oc=ownQ(nid);ownTot+=Math.min(need[nid],oc);}
  var ownMsg=needTot?' · <span style="color:'+(ownTot>=needTot?'var(--pos)':'var(--warn)')+'">◆ owned '+ownTot+'/'+needTot+' ('+Math.round(100*ownTot/needTot)+'%)</span>':'';
  var banner='<div class=deckstats>Deck <b>'+esc(St.active)+'</b> · value <b>$'+deckVal().toFixed(2)+'</b> · to finish <b>$'+comp().toFixed(2)+'</b>'+ownMsg+' · '+legal+mw+'</div>';
  ltbl_.innerHTML=banner+secTable('main','Main Deck',60,lq)+secTable('extra','Extra Deck',15,lq)+secTable('side','Side Deck',15,lq);}
function rTable(){
  if(view==='deck'){renderDeck();return;}
  if(view!=='collection'&&view!=='wishlist')return;   // guard: only list views have a table
  var m=bucket(view),lqel=document.getElementById('lq'),lq=lqel?lqel.value.toLowerCase():'';
  var total=Object.keys(m).length;
  if(!total){ltbl_.innerHTML='<div class=empty>Nothing in your '+view+' yet — go to Browse and click +'+(view==='collection'?'Coll':'Wish')+', or use “add a card” above.</div>';return;}
  var clel=document.getElementById('lclass'),cl=clel?clel.value:'all';
  var srel=document.getElementById('lsort'),sr=srel?srel.value:(view==='wishlist'?'pr':'name');
  var po={High:0,Normal:1,Low:2};
  var D=[]; Object.keys(m).forEach(function(id){var c=BY[id]; if(!c)return; if(lq&&c.n.toLowerCase().indexOf(lq)<0)return; if(cl!=='all'&&c.cl!==cl)return;
    m[id].forEach(function(ln,li){D.push({id:+id,li:li,ln:ln,c:c});});});
  var lp=function(o){var p=entPrice(o.ln,o.c);return p==null?-1:p;};
  D.sort(function(a,b){
    if(sr==='price')return lp(b)-lp(a);
    if(sr==='value')return (lp(b)<0?0:lp(b)*b.ln.q)-(lp(a)<0?0:lp(a)*a.ln.q);
    if(sr==='qty')return b.ln.q-a.ln.q;
    if(sr==='rarity')return (ORD[b.ln.rar]||-1)-(ORD[a.ln.rar]||-1);
    if(sr==='pr')return (po[a.ln.pr]||1)-(po[b.ln.pr]||1)||(a.c.n<b.c.n?-1:1);
    return a.c.n<b.c.n?-1:a.c.n>b.c.n?1:(a.li-b.li);});   // default: name
  var cnt='<div class=count>'+D.length+' line'+(D.length===1?'':'s')+' · '+total+' card'+(total===1?'':'s')+' · <span class=mut>tip: edit <b>Unit</b> to your value; <b>+ver</b> adds another rarity/condition you own</span></div>';
  if(listMode==='grid'){ltbl_.innerHTML=cnt+'<div class=grid>'+D.map(function(o){return gridTile(view,o.id,false,o.li);}).join('')+'</div>';return;}
  var rows=D.map(function(o){return listRow(view,o.id,false,o.li);}).join('');
  ltbl_.innerHTML=cnt
    +'<table><tr><th>Card</th><th>Qty</th>'+(view==='wishlist'?'<th>Priority</th>':'')
    +'<th>Rarity</th><th>Cond.</th><th class=r>Unit (yours)</th><th class=r>Value</th><th></th></tr>'+rows+'</table>';
}
function med(a){if(!a.length)return null;a=a.slice().sort(function(x,y){return x-y;});return a[Math.floor(a.length/2)];}
function grpMed(kf){var g={};PRICED.forEach(function(c){var k=kf(c);if(k==null||k==='')return;(g[k]=g[k]||[]).push(c.m);});
  return Object.keys(g).map(function(k){return {k:k,med:med(g[k]),n:g[k].length};});}
function ost(v,l){return '<div class=ost><div class=v>'+v+'</div><div class=l>'+l+'</div></div>';}
function hbar(rows){if(!rows.length)return '<div class=ins>no data</div>';var mx=Math.max.apply(0,rows.map(function(r){return r.med;}));
  return rows.map(function(r){var w=mx?100*r.med/mx:0;
    return '<div class=crow><div class=clab>'+esc(r.k)+'</div><div class=cbarwrap><div class=cbar style="width:'+w.toFixed(1)+'%"></div></div>'
      +'<div class=cval>$'+r.med.toFixed(2)+' <span class=cn>n='+r.n+'</span></div></div>';}).join('');}
function histo(){var bins=[[0,.1],[.1,.25],[.25,.5],[.5,1],[1,2],[2,5],[5,10],[10,25],[25,100],[100,1e12]];
  var labs=['<10¢','10–25¢','25–50¢','50¢–$1','$1–2','$2–5','$5–10','$10–25','$25–100','$100+'];
  var ct=bins.map(function(b){var n=0;PRICED.forEach(function(c){if(c.m>=b[0]&&c.m<b[1])n++;});return n;});
  var mx=Math.max.apply(0,ct);
  return '<div class=hist>'+ct.map(function(n,i){return '<div class=hcol><div class=hbarwrap><div class=hbar style="height:'+(mx?100*n/mx:0).toFixed(1)+'%"></div></div><div class=hn>'+n.toLocaleString()+'</div><div class=hlab>'+labs[i]+'</div></div>';}).join('')+'</div>';}
var AGEO=['0–2 yrs','2–5','5–10','10–15','15–20','20+ yrs'];
function ageB(a){if(a==null)return null;if(a<2)return AGEO[0];if(a<5)return AGEO[1];if(a<10)return AGEO[2];if(a<15)return AGEO[3];if(a<20)return AGEO[4];return AGEO[5];}
function rA(){
  var ms=PRICED.map(function(c){return c.m;});
  var mdn=med(ms),mean=ms.reduce(function(a,b){return a+b;},0)/ms.length,tot=ms.reduce(function(a,b){return a+b;},0);
  var maxc=PRICED.reduce(function(a,b){return b.m>a.m?b:a;});
  var bo={Unlimited:0,'Semi-Limited':1,Limited:2,Forbidden:3};
  var byBan=grpMed(function(c){return c.bn;}).sort(function(a,b){return bo[a.k]-bo[b.k];});
  var byRar=grpMed(function(c){return c.hr;}).filter(function(r){return r.n>=10;}).sort(function(a,b){return (ORD[a.k]||0)-(ORD[b.k]||0);});
  var byAge=grpMed(function(c){return ageB(c.ag);}).sort(function(a,b){return AGEO.indexOf(a.k)-AGEO.indexOf(b.k);});
  var byCls=grpMed(function(c){return c.cl;}).sort(function(a,b){return b.med-a.med;});
  var byArch=grpMed(function(c){return c.ar;}).filter(function(r){return r.n>=20;}).sort(function(a,b){return b.med-a.med;}).slice(0,12);
  var unl=byBan.filter(function(r){return r.k==='Unlimited';})[0],fb=byBan.filter(function(r){return r.k==='Forbidden';})[0];
  var banIns=(unl&&fb)?'Forbidden cards median $'+fb.med.toFixed(2)+' vs Unlimited $'+unl.med.toFixed(2)+' ('+(fb.med/unl.med).toFixed(1)+'× higher) — banned ≠ cheap. They’re the powerful, iconic cards collectors want (association, not proof that banning raises price).':'';
  document.getElementById('anaBody').innerHTML='<div class=ana>'
    +'<h2 style="margin-top:6px">Market overview</h2><div class=ovw>'
      +ost(PRICED.length.toLocaleString(),'priced cards')+ost('$'+mdn.toFixed(2),'median price')
      +ost('$'+mean.toFixed(2),'mean price')+ost('$'+Math.round(tot).toLocaleString(),'total market value')
      +ost(esc(maxc.n.length>22?maxc.n.slice(0,22)+'…':maxc.n),'priciest ($'+maxc.m.toFixed(0)+')')+'</div>'
    +grp('adist','Price distribution',null,'<p class=ins>Extreme right tail: median $'+mdn.toFixed(2)+' but mean $'+mean.toFixed(2)+' ('+(mean/mdn).toFixed(1)+'× higher). A handful of chase cards dominate, so the analysis uses medians, not means.</p>'+histo())
    +grp('aban','Median price by ban status',(unl&&fb)?(fb.med/unl.med).toFixed(1)+'× spread':null,'<p class=ins>'+banIns+'</p>'+hbar(byBan))
    +grp('arar','Median price by rarity',byRar.length+' rarities','<p class=ins>Rarity mostly measures print run (scarcity), not playability — a Secret Rare of a weak card can outprice a Common of a strong one.</p>'+hbar(byRar))
    +grp('aage','Median price by card age',null,'<p class=ins>Raw medians barely move with age — yet the notebook’s regression found a vintage premium once rarity and reprints were controlled for. A good reminder that a raw cut and a modeled effect can disagree.</p>'+hbar(byAge))
    +grp('atype','Median price by card type',null,hbar(byCls))
    +grp('aarch','Top archetypes by median price','top '+byArch.length,'<p class=ins>Archetypes whose cards command the highest median price (≥20 priced cards).</p>'+hbar(byArch))
    +'<p class=ins style="margin-top:20px">Computed live from '+PRICED.length.toLocaleString()+' priced cards in the current snapshot — the same analysis as the notebook, recomputed in the browser.</p></div>';
}
function spark(h){ if(!h||h.length<2)return '<span class=mut>price history builds as the collector runs ('+((h&&h.length)||0)+' day'+(((h&&h.length)===1)?'':'s')+' so far)</span>';
  var ps=h.map(function(x){return x[1];}),mn=Math.min.apply(0,ps),mx=Math.max.apply(0,ps),w=300,ht=44;
  var pts=h.map(function(x,i){var X=h.length<2?0:i/(h.length-1)*w, Y=mx===mn?ht/2:ht-(x[1]-mn)/(mx-mn)*ht; return X.toFixed(1)+','+Y.toFixed(1);}).join(' ');
  return '<svg width="'+w+'" height="'+ht+'"><polyline points="'+pts+'" fill="none" stroke="#7aa2ff" stroke-width="2"/></svg>'
    +'<div class=mut style="font-size:11px">'+h[0][0]+' → '+h[h.length-1][0]+' · $'+mn.toFixed(2)+'–$'+mx.toFixed(2)+'</div>';
}
function openM(id){var c=BY[id]; if(!c)return;
  var lvl=c.lk!=null?'LINK-'+c.lk:(c.xy?'Rank '+c.lv:(c.lv!=null&&c.lv!==0?'Lv '+c.lv:null));
  var scl=c.sc!=null?'Scale '+c.sc:null;
  var stats=[c.at,lvl,scl,c.atk!=null?'ATK '+c.atk:null,c.df!=null?'DEF '+c.df:null].filter(Boolean).join(' · ');
  var rkeys=Object.keys(c.rp).sort(function(a,b){return (ORD[a]||0)-(ORD[b]||0);});
  // FACTUAL only: mark the cheapest rarity we actually have a listed price for.
  // Do NOT assume the card market-low maps to any rarity — the feed's card-level
  // "market low" is a cheapest-copy-anywhere figure that often matches no printing price.
  var lowR=null,lowP=Infinity;
  rkeys.forEach(function(rn){var pv=c.rp[rn];if(pv!=null&&pv<lowP){lowP=pv;lowR=rn;}});
  var rt=rkeys.map(function(rn){var pv=c.rp[rn];
    var cell=pv!=null?'$'+pv.toFixed(2):'<span class=mut>—</span>';
    var tag=(rn===lowR)?' <span class=lowtag>◂ lowest listed</span>':'';
    var sets=(c.st&&c.st[rn])?'<div class=rsets title="'+eatt(c.st[rn])+'">'+esc(c.st[rn])+'</div>':'';
    return '<tr><td><span class="'+rarClass(rn)+'">'+rn+'</span>'+tag+sets+'</td><td class="r" style="vertical-align:top">'+cell+'</td></tr>';}).join('')||'<tr><td class=mut colspan=2>no printings recorded for this card</td></tr>';
  var rnote='<div class=mut style="font-size:10.5px;margin-top:4px;line-height:1.45">Per-printing prices from the free feed (~30% coverage); “—” = no listed price for that printing, and the cheapest priced one is tagged <b style="color:var(--gold)">lowest listed</b>. <b>Market low</b> above is the cheapest copy across <i>all</i> printings and isn’t tied to a specific rarity in the free data. The line under each rarity is where it was printed.</div>';
  mBody.innerHTML='<span class=close onclick="closeM()">✕</span>'
    +'<img class=cimg src="data/images/'+c.i+'.jpg" onerror="this.style.display=\'none\'">'
    +'<h2>'+esc(c.n)+'</h2><div class=sub>'+[c.cl,c.rc,stats].filter(Boolean).join(' · ')
    +(c.bn!=='Unlimited'?' · <b>'+c.bn+'</b>':'')+(c.ar?' · '+esc(c.ar):'')+(c.rd?' · released '+fdate(c.rd):'')+'</div>'
    +'<div class=tx>'+esc(c.tx)+'</div>'
    +'<div style="margin:8px 0">'+spark(c.h)+'</div>'
    +'<b style="font-size:12px;color:#9a9ab0" title="cheapest copy across all printings/rarities — not tied to one rarity">Market low (cheapest copy, any printing): $'+(c.m!=null?c.m.toFixed(2):'—')+'</b>'
    +'<table style="margin-top:4px"><tr><th>Rarity ('+rkeys.length+')</th><th class=r>Price</th></tr>'+rt+'</table>'+rnote
    +'<div class=bar><button onclick="addToDeck('+id+');">+ Deck</button><button onclick="add(\'collection\','+id+');">+ Collection</button><button onclick="add(\'wishlist\','+id+');">+ Wishlist</button></div>';
  document.getElementById('ov').style.display='flex';
}
function closeM(){document.getElementById('ov').style.display='none';}
function dl(name,text,type){var b=new Blob([text],{type:type});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name;a.click();}
function exYdk(){var d=curDeck(),out=[]; [['main','#main'],['extra','#extra'],['side','!side']].forEach(function(p){out.push(p[1]);var m=d[p[0]];for(var id in m)for(var k=0;k<m[id].q;k++)out.push(id);});
  dl((St.active.replace(/[^a-z0-9]+/gi,'_')||'deck')+'.ydk',out.join('\n')+'\n','text/plain');}
function exJson(){dl('ygo_backup.json',JSON.stringify(St,null,1),'application/json');}
function imJson(ev){var fl=ev.target.files[0]; if(!fl)return; var rd=new FileReader();
  rd.onload=function(){try{var o=JSON.parse(rd.result); localStorage.setItem(KEY,JSON.stringify(o)); location.reload();}catch(e){alert('Bad JSON');}}; rd.readAsText(fl);}
function parseYdk(txt){var sec='main',out={main:{},extra:{},side:{}};
  txt.split(/\r?\n/).forEach(function(ln){ln=ln.trim();var lc=ln.toLowerCase();
    if(lc.indexOf('#extra')===0)sec='extra'; else if(lc.indexOf('!side')===0)sec='side'; else if(lc.indexOf('#main')===0)sec='main';
    else if(/^\d+$/.test(ln)){var id=+ln; if(BY[id]){var s=sec==='side'?'side':(BY[id].ex?'extra':'main'); out[s][id]=(out[s][id]||0)+1;}}});
  return out;}
function parseTextList(txt){var out={};txt.split(/\r?\n/).forEach(function(ln){ln=ln.trim();if(!ln||ln.charAt(0)==='#')return;
  var q=1,name=ln,m=ln.match(/^(\d+)\s*[xX]?\s+(.+)$/)||ln.match(/^(.+?)\s*[xX]\s*(\d+)$/);
  if(m){if(/^\d+$/.test(m[1])){q=+m[1];name=m[2];}else{name=m[1];q=+m[2];}}
  var id=NAME2ID[name.trim().toLowerCase()]; if(id)out[id]=(out[id]||0)+q;});return out;}
function importList(ev){var fl=ev.target.files[0]; if(!fl)return; var rd=new FileReader();
  rd.onload=function(){var txt=rd.result,isYdk=/#main|#extra|!side/i.test(txt)||/^\s*\d+\s*$/m.test(txt);
    if(view==='deck'){
      var secs=isYdk?parseYdk(txt):(function(){var t=parseTextList(txt),o={main:{},extra:{},side:{}};for(var id in t)o[BY[id].ex?'extra':'main'][id]=t[id];return o;})();
      var nm=(fl.name.replace(/\.(ydk|txt)$/i,'')||'Imported deck'); if(St.decks[nm])nm=nm+' ('+Object.keys(St.decks).length+')';
      var nd={main:{},extra:{},side:{}};['main','extra','side'].forEach(function(s){for(var id in secs[s])nd[s][id]={q:secs[s][id],rar:'__m'};});
      St.decks[nm]=nd;St.active=nm;sv();go('deck');
      alert('Imported deck “'+nm+'” — '+(Object.keys(secs.main).length+Object.keys(secs.extra).length+Object.keys(secs.side).length)+' unique cards.');
    }else{
      var counts={};
      if(isYdk){var s=parseYdk(txt);['main','extra','side'].forEach(function(sec){for(var id in s[sec])counts[id]=(counts[id]||0)+s[sec][id];});}
      else counts=parseTextList(txt);
      var m=bucket(view),n=0;for(var id in counts){if(isMulti(view)){var arr=m[id]||(m[id]=[]),ln=null;for(var i=0;i<arr.length;i++)if(arr[i].rar==='__m'&&!arr[i].cond){ln=arr[i];break;}if(ln)ln.q+=counts[id];else arr.push({rar:'__m',cond:'',q:counts[id]});}else{if(m[id])m[id].q+=counts[id];else m[id]={q:counts[id],rar:'__m'};}n++;}
      sv();kpis();rTable();alert('Imported '+n+' cards into your '+view+'.');
    }
    ev.target.value='';}; rd.readAsText(fl);}

var q_=document.getElementById('q'),qa_=document.getElementById('qa'),rar_=document.getElementById('rar'),cl_=document.getElementById('cl'),
bn_=document.getElementById('bn'),pmin_=document.getElementById('pmin'),pmax_=document.getElementById('pmax'),deal_=document.getElementById('deal'),
cnt_=document.getElementById('cnt'),tb_=document.getElementById('tb'),ltbl_=document.getElementById('ltbl'),lctrl_=document.getElementById('lctrl'),imp=document.getElementById('imp'),setsBody=document.getElementById('setsBody'),metaBody=document.getElementById('metaBody');
kpis(); go('menu');
addEventListener('wheel',function(e){var a=document.activeElement;if(a&&a.type==='number'&&a===e.target)a.blur();},{passive:true});
(function(){var cv=document.getElementById('bg');if(!cv)return;var cx=cv.getContext('2d'),W,H,ps=[];
function rs(){W=cv.width=innerWidth;H=cv.height=innerHeight;}addEventListener('resize',rs);rs();
var C=['143,220,255','232,198,106','150,180,255','120,220,190'];
for(var i=0;i<54;i++)ps.push({x:Math.random()*W,y:Math.random()*H,r:Math.random()*1.8+.5,vx:(Math.random()-.5)*.1,vy:-(Math.random()*.16+.03),a:Math.random()*.45+.12,c:C[i%4],ph:Math.random()*6.28});
function tick(t){cx.clearRect(0,0,W,H);for(var i=0;i<ps.length;i++){var p=ps[i];p.x+=p.vx;p.y+=p.vy;
  if(p.y<-12){p.y=H+12;p.x=Math.random()*W;}if(p.x<-12)p.x=W+12;if(p.x>W+12)p.x=-12;
  var tw=p.a*(.55+.45*Math.sin(t/950+p.ph)),R=p.r*6;
  var g=cx.createRadialGradient(p.x,p.y,0,p.x,p.y,R);g.addColorStop(0,'rgba('+p.c+','+tw+')');g.addColorStop(1,'rgba('+p.c+',0)');
  cx.fillStyle=g;cx.beginPath();cx.arc(p.x,p.y,R,0,6.283);cx.fill();}
  requestAnimationFrame(tick);}requestAnimationFrame(tick);})();
</script></body></html>"""

if __name__ == "__main__":
    main()
