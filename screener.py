#!/usr/bin/env python3
"""
Phase 1 — card screener. Reads the latest snapshot from data/ygo.db and writes a
self-contained, interactive screener.html: filter / sort / search your whole catalog by
price, rarity, ban status, archetype, age, and a cross-marketplace "gap" flag (cards priced
much lower on TCGplayer than the other USD marketplaces — a possible, noisy, buy signal).

  python3 screener.py            # regenerate from newest snapshot in the DB
Stdlib only — no venv needed.
"""
import sqlite3, os, json, datetime, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "data", "ygo.db")
TODAY = datetime.date(2026, 8, 6)

def age_years(s):
    try: return round((TODAY - datetime.date.fromisoformat(s)).days/365.25, 1)
    except (TypeError, ValueError): return None

def main():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    date = con.execute("SELECT MAX(snapshot_date) FROM price_history").fetchone()[0]
    rows = con.execute("""
        SELECT c.name, c.card_class, c.race, c.attribute, c.top_rarity_tier, c.num_printings,
               c.ban_tcg, c.archetype, c.tcg_date,
               p.tcgplayer, p.cardmarket, p.ebay, p.amazon, p.coolstuffinc
        FROM price_history p JOIN cards c USING(card_id)
        WHERE p.snapshot_date = ?""", [date]).fetchall()
    con.close()

    data, flagged = [], 0
    for r in rows:
        tcg = r["tcgplayer"]
        others = [x for x in (r["ebay"], r["amazon"], r["coolstuffinc"]) if x and x > 0]
        ref = round(statistics.median(others), 2) if others else None
        gap = round(ref / tcg, 2) if (tcg and tcg > 0 and ref) else None
        is_deal = bool(gap and gap >= 2 and tcg and tcg >= 2)   # TCG >=2x cheaper than peers, real money
        if is_deal: flagged += 1
        data.append({
            "n": r["name"], "cl": r["card_class"], "rc": r["race"], "at": r["attribute"],
            "rr": r["top_rarity_tier"], "np": r["num_printings"], "bn": r["ban_tcg"],
            "ar": r["archetype"] or "", "ag": age_years(r["tcg_date"]),
            "tcg": tcg, "oth": ref, "gap": gap, "deal": is_deal,
            "cm": r["cardmarket"],
        })

    payload = json.dumps(data).replace("</", "<\\/")
    html = HTML.replace("__DATE__", date).replace("__N__", str(len(data))).replace("__FLAG__", str(flagged)).replace("__DATA__", payload)
    out = os.path.join(HERE, "screener.html")
    open(out, "w").write(html)
    print(f"snapshot {date} | {len(data):,} cards | {flagged} cross-market gap flags")
    print(f"wrote {out} — open it in a browser (double-click, or: open screener.html)")

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>YGO Screener — __DATE__</title>
<style>
:root{--bg:#0f1020;--card:#1a1b2e;--ink:#e8e8f0;--mut:#9a9ab0;--line:#2a2b45;--pos:#5fd08a;--acc:#7aa2ff}
*{box-sizing:border-box}
body{font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
header{padding:14px 20px;border-bottom:1px solid var(--line)}
h1{margin:0;font-size:18px}.meta{color:var(--mut);font-size:12px;margin-top:2px}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:12px 20px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
input,select{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:6px 9px;font-size:13px}
input[type=text]{width:200px} .num{width:78px}
label{color:var(--mut);font-size:12px;display:flex;gap:5px;align-items:center}
.wrap{padding:0 20px 40px} .count{color:var(--mut);margin:10px 0;font-size:12px}
table{border-collapse:collapse;width:100%} th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{position:sticky;top:57px;background:var(--bg);cursor:pointer;user-select:none;color:var(--mut);font-weight:600}
th:hover{color:var(--ink)} td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}
tr:hover td{background:#181934} .nm{font-weight:600} .mut{color:var(--mut)}
.deal{color:var(--pos);font-weight:700} .pill{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:2px 8px;font-size:11px}
.warn{background:#211d0e;border:1px solid #6b5d17;color:#e8d98a;padding:8px 20px;font-size:12px}
</style></head><body>
<header><h1>Yu-Gi-Oh! Screener</h1><div class="meta">snapshot __DATE__ · __N__ cards · __FLAG__ cross-market gap flags · TCGplayer prices</div></header>
<div class="warn"><b>Cross-market “gap”</b> = TCGplayer priced ≥2× cheaper than the median of eBay/Amazon/CoolStuffInc (and ≥ $2). It’s a <i>possible</i> deal, but noisy — gaps often mean a stale or thin listing, not free money. Verify before buying.</div>
<div class="controls">
  <input type="text" id="q" placeholder="search name…" oninput="render()">
  <input type="text" id="qa" placeholder="archetype…" oninput="render()">
  <select id="cl" onchange="render()"><option value="">class: all</option><option>Monster</option><option>Spell</option><option>Trap</option></select>
  <select id="bn" onchange="render()"><option value="">ban: all</option><option>Unlimited</option><option>Semi-Limited</option><option>Limited</option><option>Forbidden</option></select>
  <label>rarity ≥ <select id="rr" onchange="render()"><option value="0">0</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select></label>
  <label>$ min <input type="text" class="num" id="pmin" value="" oninput="render()"></label>
  <label>$ max <input type="text" class="num" id="pmax" value="" oninput="render()"></label>
  <label><input type="checkbox" id="deal" onchange="render()"> gap deals only</label>
</div>
<div class="wrap"><div class="count" id="count"></div>
<table><thead><tr>
<th onclick="sort('n')">Card</th><th onclick="sort('cl')">Class</th><th onclick="sort('rc')">Type</th>
<th onclick="sort('bn')">Ban</th><th onclick="sort('ar')">Archetype</th>
<th class="r" onclick="sort('rr')">Rar</th><th class="r" onclick="sort('np')">#Pr</th><th class="r" onclick="sort('ag')">Age</th>
<th class="r" onclick="sort('tcg')">TCG $</th><th class="r" onclick="sort('oth')">Others~</th><th class="r" onclick="sort('gap')">Gap×</th>
</tr></thead><tbody id="tb"></tbody></table></div>
<script>
var DATA=__DATA__, sk="tcg", sd=-1, LIMIT=300;
function num(x){var v=parseFloat(x);return isNaN(v)?null:v}
function sort(k){sd=(sk===k)?-sd:1;sk=k;render()}
function render(){
  var q=document.getElementById('q').value.toLowerCase(), qa=document.getElementById('qa').value.toLowerCase();
  var cl=document.getElementById('cl').value, bn=document.getElementById('bn').value, rr=+document.getElementById('rr').value;
  var pmin=num(document.getElementById('pmin').value), pmax=num(document.getElementById('pmax').value), dealOnly=document.getElementById('deal').checked;
  var f=DATA.filter(function(d){
    if(q&&d.n.toLowerCase().indexOf(q)<0)return false;
    if(qa&&d.ar.toLowerCase().indexOf(qa)<0)return false;
    if(cl&&d.cl!==cl)return false; if(bn&&d.bn!==bn)return false;
    if(d.rr<rr)return false;
    if(pmin!=null&&(d.tcg==null||d.tcg<pmin))return false;
    if(pmax!=null&&(d.tcg==null||d.tcg>pmax))return false;
    if(dealOnly&&!d.deal)return false; return true;});
  f.sort(function(a,b){var x=a[sk],y=b[sk];
    if(x==null)return 1; if(y==null)return -1;
    if(typeof x==='string')return x.localeCompare(y)*sd; return (x-y)*sd;});
  document.getElementById('count').textContent=f.length.toLocaleString()+' cards match'+(f.length>LIMIT?' (showing first '+LIMIT+')':'');
  var h=f.slice(0,LIMIT).map(function(d){
    return '<tr><td class="nm">'+esc(d.n)+'</td><td>'+d.cl+'</td><td class="mut">'+(d.rc||'')+'</td>'
    +'<td>'+(d.bn==='Unlimited'?'<span class=mut>—</span>':'<span class=pill>'+d.bn+'</span>')+'</td>'
    +'<td class="mut">'+esc(d.ar)+'</td><td class="r">'+d.rr+'</td><td class="r">'+d.np+'</td>'
    +'<td class="r mut">'+(d.ag==null?'':d.ag)+'</td>'
    +'<td class="r">'+(d.tcg==null?'':'$'+d.tcg.toFixed(2))+'</td>'
    +'<td class="r mut">'+(d.oth==null?'':'$'+d.oth.toFixed(2))+'</td>'
    +'<td class="r '+(d.deal?'deal':'mut')+'">'+(d.gap==null?'':d.gap+'×')+'</td></tr>';}).join('');
  document.getElementById('tb').innerHTML=h;
}
function esc(s){return (s||'').replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})}
render();
</script></body></html>"""

if __name__ == "__main__":
    main()
