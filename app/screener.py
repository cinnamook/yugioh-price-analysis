#!/usr/bin/env python3
"""
Phase 1 — card screener (rarity-aware). Reads the latest snapshot from data/ygo.db and writes a
self-contained screener.html. Two price columns, always visible:
  • Market low  — the card-level cheapest TCGplayer listing (well covered, ~96%).
  • Rarity      — the price of the rarity you pick in the dropdown (from per-printing data; sparse
                  for premium rarities, shown as "—" when the source has none).
Plus a card-level cross-market "gap" flag (TCGplayer >=2x under the eBay/Amazon/CoolStuffInc median).

  python3 app/screener.py   (run pipeline/collect_snapshot.py once first if the card_rarities table is missing)
Stdlib only.
"""
import sqlite3, os, sys, json, datetime, statistics
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))   # app/
ROOT = os.path.dirname(HERE)                        # repo root — data/ and the generated pages live there
# RARITY_ORDER is owned by the collector, which lives in pipeline/. No package, so put it on the path.
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from collect_snapshot import RARITY_ORDER

DB   = os.path.join(ROOT, "data", "ygo.db")
TODAY = datetime.date.today()   # card "age" is relative to the build, not a frozen date
IDX = {name: i for i, name in enumerate(RARITY_ORDER)}

def age_years(s):
    try: return round((TODAY - datetime.date.fromisoformat(s)).days/365.25, 1)
    except (TypeError, ValueError): return None

def main():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    has = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='card_rarities'").fetchone()
    if not has or con.execute("SELECT COUNT(*) FROM card_rarities").fetchone()[0] == 0:
        print("No per-rarity data in the DB yet. Run this once first (it adds the rarity table):\n"
              "    python3 pipeline/collect_snapshot.py"); return
    date = con.execute("SELECT MAX(snapshot_date) FROM price_history").fetchone()[0]
    cards = con.execute("""
        SELECT c.card_id, c.name, c.card_class, c.race, c.num_printings, c.ban_tcg, c.archetype, c.tcg_date,
               p.tcgplayer, p.ebay, p.amazon, p.coolstuffinc
        FROM price_history p JOIN cards c USING(card_id) WHERE p.snapshot_date=?""", [date]).fetchall()
    rar = defaultdict(dict)
    for r in con.execute("SELECT card_id, rarity, price FROM card_rarities").fetchall():
        i = IDX.get(r["rarity"])
        if i is not None: rar[r["card_id"]][i] = r["price"]
    con.close()

    data, flagged = [], 0
    for c in cards:
        tcg = c["tcgplayer"]
        others = [x for x in (c["ebay"], c["amazon"], c["coolstuffinc"]) if x and x > 0]
        ref = round(statistics.median(others), 2) if others else None
        gap = round(ref/tcg, 2) if (tcg and tcg > 0 and ref) else None
        deal = bool(gap and gap >= 2 and tcg and tcg >= 2)
        if deal: flagged += 1
        rp = rar.get(c["card_id"], {})
        hidx = max(rp) if rp else None
        data.append({"n": c["name"], "cl": c["card_class"], "rc": c["race"], "bn": c["ban_tcg"],
                     "ar": c["archetype"] or "", "ag": age_years(c["tcg_date"]), "np": c["num_printings"],
                     "tcg": tcg, "oth": ref, "gap": gap, "deal": deal,
                     "hr": RARITY_ORDER[hidx] if hidx is not None else None,
                     "hrp": rp.get(hidx) if hidx is not None else None,
                     "rp": {str(k): v for k, v in rp.items()}})

    payload = json.dumps(data).replace("</", "<\\/")
    html = (HTML.replace("__DATE__", date).replace("__N__", str(len(data))).replace("__FLAG__", str(flagged))
            .replace("__RARJSON__", json.dumps(RARITY_ORDER)).replace("__DATA__", payload))
    out = os.path.join(ROOT, "screener.html"); open(out, "w").write(html)
    print(f"snapshot {date} | {len(data):,} cards | {len(RARITY_ORDER)} rarities | {flagged} gap flags")
    print(f"wrote {out} — open it in a browser (double-click, or: open screener.html)")

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>YGO Screener — __DATE__</title>
<style>
:root{--bg:#0f1020;--card:#1a1b2e;--ink:#e8e8f0;--mut:#9a9ab0;--line:#2a2b45;--pos:#5fd08a;--acc:#7aa2ff}
*{box-sizing:border-box} body{font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
header{padding:14px 20px;border-bottom:1px solid var(--line)} h1{margin:0;font-size:18px}
.meta{color:var(--mut);font-size:12px;margin-top:2px}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:12px 20px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
input,select{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:6px 9px;font-size:13px}
input[type=text]{width:170px} .num{width:70px}
label{color:var(--mut);font-size:12px;display:flex;gap:5px;align-items:center}
.wrap{padding:0 20px 40px} .count{color:var(--mut);margin:10px 0;font-size:12px}
table{border-collapse:collapse;width:100%} th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{position:sticky;top:57px;background:var(--bg);cursor:pointer;user-select:none;color:var(--mut);font-weight:600}
th:hover{color:var(--ink)} td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}
th.rar,td.rar{color:var(--acc)} tr:hover td{background:#181934} .nm{font-weight:600} .mut{color:var(--mut)}
.deal{color:var(--pos);font-weight:700} .pill{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:2px 8px;font-size:11px}
.warn{background:#211d0e;border:1px solid #6b5d17;color:#e8d98a;padding:8px 20px;font-size:12px}
.warn b{color:#f4d97a}
</style></head><body>
<header><h1>Yu-Gi-Oh! Screener</h1><div class="meta">snapshot __DATE__ · __N__ cards · __FLAG__ cross-market gap flags · TCGplayer prices</div></header>
<div class="warn"><b>Market low</b> = cheapest listing for the card (any printing). <b>Rarity</b> = the price of the
rarity you pick in the dropdown (sparse for premium rarities — shown “—” when the source has no price; pick a
rarity to also filter to cards printed in it). <b>Mkt~</b> = median of eBay/Amazon/CoolStuffInc; <b>Gap×</b> flags
TCGplayer ≥2× under that (a <i>possible</i>, noisy deal).</div>
<div class="controls">
  <input type="text" id="q" placeholder="search name…" oninput="render()">
  <input type="text" id="qa" placeholder="archetype…" oninput="render()">
  <select id="rar" onchange="render()"></select>
  <select id="cl" onchange="render()"><option value="">class: all</option><option>Monster</option><option>Spell</option><option>Trap</option></select>
  <select id="bn" onchange="render()"><option value="">ban: all</option><option>Unlimited</option><option>Semi-Limited</option><option>Limited</option><option>Forbidden</option></select>
  <label>$ min <input type="text" class="num" id="pmin" oninput="render()"></label>
  <label>$ max <input type="text" class="num" id="pmax" oninput="render()"></label>
  <label><input type="checkbox" id="pon" onchange="render()"> priced only</label>
  <label><input type="checkbox" id="deal" onchange="render()"> gap deals only</label>
</div>
<div class="wrap"><div class="count" id="count"></div>
<table><thead><tr>
<th onclick="srt('n')">Card</th><th onclick="srt('cl')">Class</th><th onclick="srt('rc')">Type</th>
<th onclick="srt('bn')">Ban</th><th onclick="srt('ar')">Archetype</th><th onclick="srt('hr')">Top rarity</th>
<th class="r" onclick="srt('np')">#Pr</th><th class="r" onclick="srt('ag')">Age</th>
<th class="r" onclick="srt('market')">Market low $</th>
<th class="r rar" id="ph" onclick="srt('rarity')">Rarity $</th>
<th class="r" onclick="srt('oth')" title="median of eBay, Amazon, CoolStuffInc">Mkt~</th>
<th class="r" onclick="srt('gap')">Gap×</th>
</tr></thead><tbody id="tb"></tbody></table></div>
<script>
var DATA=__DATA__, RAR=__RARJSON__, sk="market", sd=-1, LIMIT=300;
(function(){document.getElementById('rar').innerHTML='<option value="">rarity: any</option>'+
  RAR.map(function(r,i){return '<option value="'+i+'">'+r+'</option>';}).join('');})();
function numv(x){var v=parseFloat(x);return isNaN(v)?null:v}
function rarityPrice(d,rs){ if(rs==='')return d.hrp; return (rs in d.rp)?d.rp[rs]:null; }
function activePrice(d,rs){ return rs===''? d.tcg : rarityPrice(d,rs); }
function srt(k){sd=(sk===k)?-sd:1;sk=k;render()}
function render(){
  var q=q_.value.toLowerCase(),qa=qa_.value.toLowerCase(),rs=rar_.value,cl=cl_.value,bn=bn_.value;
  var pmin=numv(pmin_.value),pmax=numv(pmax_.value),pon=pon_.checked,dealOnly=deal_.checked;
  document.getElementById('ph').textContent=(rs===''?'Top-rarity':RAR[rs])+' $';
  var view=[];
  for(var i=0;i<DATA.length;i++){var d=DATA[i];
    if(q&&d.n.toLowerCase().indexOf(q)<0)continue;
    if(qa&&d.ar.toLowerCase().indexOf(qa)<0)continue;
    if(cl&&d.cl!==cl)continue; if(bn&&d.bn!==bn)continue;
    if(rs!==''&&!(rs in d.rp))continue;                 // only cards printed in the chosen rarity
    var act=activePrice(d,rs);
    if(pon&&act==null)continue;
    if(pmin!=null&&(act==null||act<pmin))continue;
    if(pmax!=null&&(act==null||act>pmax))continue;
    if(dealOnly&&!d.deal)continue;
    view.push({d:d,rar:rarityPrice(d,rs)});
  }
  view.sort(function(a,b){
    var x = sk==='market'?a.d.tcg : sk==='rarity'?a.rar : a.d[sk];
    var y = sk==='market'?b.d.tcg : sk==='rarity'?b.rar : b.d[sk];
    if(x==null)return 1; if(y==null)return -1;
    if(typeof x==='string')return x.localeCompare(y)*sd; return (x-y)*sd;});
  var priced=view.filter(function(v){return v.rar!=null;}).length;
  count_.textContent=view.length.toLocaleString()+' cards match'+(rs!==''?' · '+priced+' with a '+RAR[rs]+' price':'')+(view.length>LIMIT?' (showing first '+LIMIT+')':'');
  tb_.innerHTML=view.slice(0,LIMIT).map(function(v){var d=v.d;
    return '<tr><td class="nm">'+esc(d.n)+'</td><td>'+d.cl+'</td><td class="mut">'+(d.rc||'')+'</td>'
    +'<td>'+(d.bn==='Unlimited'?'<span class=mut>—</span>':'<span class=pill>'+d.bn+'</span>')+'</td>'
    +'<td class="mut">'+esc(d.ar)+'</td><td class="mut">'+(d.hr||'')+'</td>'
    +'<td class="r">'+d.np+'</td><td class="r mut">'+(d.ag==null?'':d.ag)+'</td>'
    +'<td class="r">'+(d.tcg==null?'<span class=mut>—</span>':'$'+d.tcg.toFixed(2))+'</td>'
    +'<td class="r rar">'+(v.rar==null?'<span class=mut>—</span>':'$'+v.rar.toFixed(2))+'</td>'
    +'<td class="r mut">'+(d.oth==null?'':'$'+d.oth.toFixed(2))+'</td>'
    +'<td class="r '+(d.deal?'deal':'mut')+'">'+(d.gap==null?'':d.gap+'×')+'</td></tr>';}).join('');
}
function esc(s){return (s||'').replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})}
var q_=document.getElementById('q'),qa_=document.getElementById('qa'),rar_=document.getElementById('rar'),
cl_=document.getElementById('cl'),bn_=document.getElementById('bn'),pmin_=document.getElementById('pmin'),
pmax_=document.getElementById('pmax'),pon_=document.getElementById('pon'),deal_=document.getElementById('deal'),
count_=document.getElementById('count'),tb_=document.getElementById('tb');
render();
</script></body></html>"""

if __name__ == "__main__":
    main()
