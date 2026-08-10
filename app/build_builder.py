#!/usr/bin/env python3
"""
Interactive Collection / Deck / Wishlist builder. Reads the latest snapshot from data/ygo.db and
writes builder.html — a self-contained app: search cards, add them to your Collection, a Deck, or a
Wishlist, pick a rarity per line, and see live totals including cost-to-complete-the-deck. Your lists
save in the browser (localStorage) and can be exported/imported as JSON, or the deck as .ydk.

  python3 app/build_builder.py (run pipeline/collect_snapshot.py once first if card_rarities is missing)
Stdlib only.
"""
import sqlite3, os, sys, json
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))   # app/
ROOT = os.path.dirname(HERE)                        # repo root — data/ and the generated pages live there
# RARITY_ORDER is owned by the collector, which lives in pipeline/. No package, so put it on the path.
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from collect_snapshot import RARITY_ORDER

DB   = os.path.join(ROOT, "data", "ygo.db")

def main():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    if not con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='card_rarities'").fetchone():
        print("Run  python3 pipeline/collect_snapshot.py  once first (adds the rarity table)."); return
    date = con.execute("SELECT MAX(snapshot_date) FROM price_history").fetchone()[0]
    rows = con.execute("""SELECT c.card_id, c.name, c.card_class, c.race, p.tcgplayer
                          FROM price_history p JOIN cards c USING(card_id) WHERE p.snapshot_date=?""", [date]).fetchall()
    rp = defaultdict(dict)
    for r in con.execute("SELECT card_id, rarity, price FROM card_rarities WHERE price IS NOT NULL").fetchall():
        rp[r["card_id"]][r["rarity"]] = r["price"]
    con.close()

    cards = [{"i": r["card_id"], "n": r["name"], "cl": r["card_class"], "rc": r["race"],
              "m": r["tcgplayer"], "r": rp.get(r["card_id"], {})} for r in rows]
    payload = json.dumps(cards).replace("</", "<\\/")
    html = HTML.replace("__DATE__", date).replace("__DATA__", payload)
    out = os.path.join(ROOT, "builder.html"); open(out, "w").write(html)
    print(f"snapshot {date} | {len(cards):,} cards embedded")
    print(f"wrote {out} — open it (double-click, or: open builder.html). Your lists save in the browser.")

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>YGO Builder — __DATE__</title><style>
:root{--bg:#0f1020;--card:#1a1b2e;--ink:#e8e8f0;--mut:#9a9ab0;--line:#2a2b45;--pos:#5fd08a;--acc:#7aa2ff;--warn:#e8b45f}
*{box-sizing:border-box}body{font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
header{padding:12px 18px;border-bottom:1px solid var(--line);display:flex;gap:14px;align-items:center;flex-wrap:wrap}
h1{margin:0;font-size:17px}.meta{color:var(--mut);font-size:12px}
.kpis{display:flex;gap:10px;margin-left:auto;flex-wrap:wrap}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:6px 12px;text-align:right}
.kpi .v{font-size:16px;font-weight:700}.kpi.hl .v{color:var(--pos)}.kpi .l{color:var(--mut);font-size:10px;text-transform:uppercase;letter-spacing:.04em}
.main{display:grid;grid-template-columns:minmax(340px,1fr) 1.3fr;gap:0;height:calc(100vh - 58px)}
.pane{overflow:auto;padding:14px 16px}.pane.left{border-right:1px solid var(--line)}
input,select,button{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:6px 9px;font-size:13px;font-family:inherit}
#q{width:100%;margin-bottom:10px;padding:9px 11px}
.res{display:flex;align-items:center;gap:8px;padding:5px 6px;border-bottom:1px solid var(--line)}
.res .nm{flex:1;font-weight:600}.res .pr{color:var(--mut);font-variant-numeric:tabular-nums}
.res button{padding:3px 8px;font-size:11px;cursor:pointer}.res button:hover{border-color:var(--acc);color:var(--acc)}
.tabs{display:flex;gap:6px;margin-bottom:10px}
.tab{padding:6px 12px;border-radius:7px;cursor:pointer;border:1px solid var(--line);background:var(--card)}
.tab.on{border-color:var(--acc);color:var(--acc)}
table{border-collapse:collapse;width:100%}td,th{padding:5px 7px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mut);font-weight:600;font-size:12px}.r{text-align:right;font-variant-numeric:tabular-nums}
.qbtn{cursor:pointer;padding:1px 7px}.x{cursor:pointer;color:var(--mut)}.x:hover{color:#e0607a}
.empty{color:var(--mut);padding:20px 4px}.bar{display:flex;gap:8px;margin:12px 0 4px}
.bar button{cursor:pointer;font-size:12px}.mut{color:var(--mut)}.rsel{font-size:11px;padding:2px 4px}
</style></head><body>
<header><h1>YGO Builder</h1><span class="meta">snapshot __DATE__ · lists save in this browser</span>
<div class="kpis">
  <div class="kpi"><div class="v" id="kColl">$0</div><div class="l">Collection</div></div>
  <div class="kpi"><div class="v" id="kDeck">$0</div><div class="l">Deck value</div></div>
  <div class="kpi hl"><div class="v" id="kComp">$0</div><div class="l">Cost to finish</div></div>
  <div class="kpi"><div class="v" id="kWish">$0</div><div class="l">Wishlist</div></div>
</div></header>
<div class="main">
  <div class="pane left">
    <input id="q" placeholder="search cards to add…" oninput="search()">
    <div id="results"></div>
  </div>
  <div class="pane right">
    <div class="tabs">
      <div class="tab on" data-t="deck" onclick="tab('deck')">Deck</div>
      <div class="tab" data-t="collection" onclick="tab('collection')">Collection</div>
      <div class="tab" data-t="wishlist" onclick="tab('wishlist')">Wishlist</div>
    </div>
    <div id="list"></div>
    <div class="bar">
      <button onclick="exportYdk()">Export deck .ydk</button>
      <button onclick="exportJson()">Backup (.json)</button>
      <button onclick="document.getElementById('imp').click()">Import .json</button>
      <input id="imp" type="file" accept=".json" style="display:none" onchange="importJson(event)">
    </div>
  </div>
</div>
<script>
var CARDS=__DATA__, BY={}; CARDS.forEach(function(c){BY[c.i]=c;});
var KEY="ygo_builder_v1", cur="deck";
var S=load();
function load(){try{return JSON.parse(localStorage.getItem(KEY))||blank();}catch(e){return blank();}}
function blank(){return {deck:{},collection:{},wishlist:{}};}
function save(){localStorage.setItem(KEY,JSON.stringify(S));}
function priceOf(c,rar){ if(!rar||rar==='__m'||!(rar in c.r)) return c.m; return c.r[rar]; }
function esc(s){return (s||'').replace(/[&<>]/g,function(x){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[x]});}
function fmt(v){return v==null?'—':'$'+v.toFixed(2);}

function search(){
  var v=document.getElementById('q').value.toLowerCase();
  var out=document.getElementById('results');
  if(v.length<2){out.innerHTML='<div class=empty>Type at least 2 letters to search '+CARDS.length.toLocaleString()+' cards.</div>';return;}
  var hits=[],i=0; for(;i<CARDS.length&&hits.length<50;i++){ if(CARDS[i].n.toLowerCase().indexOf(v)>=0)hits.push(CARDS[i]); }
  out.innerHTML=hits.map(function(c){return '<div class=res><span class=nm>'+esc(c.n)+'</span>'
    +'<span class=pr>'+fmt(c.m)+'</span>'
    +'<button onclick="add(\'deck\','+c.i+')">+Deck</button>'
    +'<button onclick="add(\'collection\','+c.i+')">+Coll</button>'
    +'<button onclick="add(\'wishlist\','+c.i+')">+Wish</button></div>';}).join('')
    ||'<div class=empty>No matches.</div>';
}
function add(list,id){ var m=S[list]; if(m[id])m[id].q++; else m[id]={q:1,rar:'__m'}; save(); render(); }
function setQ(list,id,dq){ var e=S[list][id]; if(!e)return; e.q+=dq; if(e.q<=0)delete S[list][id]; save(); render(); }
function setRar(list,id,rar){ if(S[list][id]){S[list][id].rar=rar; save(); render();} }
function del(list,id){ delete S[list][id]; save(); render(); }
function tab(t){cur=t; document.querySelectorAll('.tab').forEach(function(x){x.classList.toggle('on',x.dataset.t===t);}); render();}

function lineTotal(list){var s=0; var m=S[list]; for(var id in m){var c=BY[id]; if(!c)continue; var p=priceOf(c,m[id].rar); if(p!=null)s+=p*m[id].q;} return s;}
function completeCost(){var s=0,d=S.deck,coll=S.collection; for(var id in d){var c=BY[id]; if(!c)continue;
  var own=coll[id]?coll[id].q:0, buy=Math.max(0,d[id].q-own), p=priceOf(c,d[id].rar); if(p!=null)s+=p*buy;} return s;}

function render(){
  document.getElementById('kColl').textContent='$'+lineTotal('collection').toFixed(2);
  document.getElementById('kDeck').textContent='$'+lineTotal('deck').toFixed(2);
  document.getElementById('kWish').textContent='$'+lineTotal('wishlist').toFixed(2);
  document.getElementById('kComp').textContent='$'+completeCost().toFixed(2);
  var m=S[cur], ids=Object.keys(m);
  if(!ids.length){document.getElementById('list').innerHTML='<div class=empty>Nothing in your '+cur+' yet — search on the left and click +'+(cur==='deck'?'Deck':cur==='collection'?'Coll':'Wish')+'.</div>';return;}
  var showOwn = cur==='deck';
  var rows=ids.map(function(id){var c=BY[id]; if(!c)return ''; var e=m[id]; var p=priceOf(c,e.rar);
    var rars=['<option value="__m"'+(e.rar==='__m'?' selected':'')+'>Market low</option>']
      .concat(Object.keys(c.r).map(function(rn){return '<option'+(e.rar===rn?' selected':'')+'>'+rn+'</option>';})).join('');
    var own = showOwn ? (S.collection[id]?S.collection[id].q:0) : null;
    var buy = showOwn ? Math.max(0,e.q-own) : null;
    return '<tr><td class=nm>'+esc(c.n)+'</td>'
      +'<td><span class=qbtn onclick="setQ(\''+cur+'\','+id+',-1)">–</span> '+e.q+' <span class=qbtn onclick="setQ(\''+cur+'\','+id+',1)">+</span></td>'
      +(showOwn?'<td class="r mut">'+own+'</td><td class="r">'+buy+'</td>':'')
      +'<td><select class=rsel onchange="setRar(\''+cur+'\','+id+',this.value)">'+rars+'</select></td>'
      +'<td class="r">'+fmt(p)+'</td><td class="r">'+fmt(p==null?null:p*(showOwn?buy:e.q))+'</td>'
      +'<td class=x onclick="del(\''+cur+'\','+id+')">✕</td></tr>';}).join('');
  var head='<tr><th>Card</th><th>Qty</th>'+(showOwn?'<th class=r>Own</th><th class=r>Buy</th>':'')
    +'<th>Rarity</th><th class=r>Unit</th><th class=r>'+(showOwn?'To-buy':'Value')+'</th><th></th></tr>';
  document.getElementById('list').innerHTML='<table>'+head+rows+'</table>';
}
function dl(name,text,type){var b=new Blob([text],{type:type});var a=document.createElement('a');
  a.href=URL.createObjectURL(b);a.download=name;a.click();}
function exportYdk(){var l=['#main']; for(var id in S.deck){for(var k=0;k<S.deck[id].q;k++)l.push(id);} l.push('#extra','!side');
  dl('deck.ydk',l.join('\n')+'\n','text/plain');}
function exportJson(){dl('ygo_builder_backup.json',JSON.stringify(S,null,1),'application/json');}
function importJson(ev){var f=ev.target.files[0]; if(!f)return; var r=new FileReader();
  r.onload=function(){try{S=JSON.parse(r.result); if(!S.deck||!S.collection||!S.wishlist)S=blank(); save(); render();}catch(e){alert('Bad JSON file');}}; r.readAsText(f);}
search(); render();
</script></body></html>"""

if __name__ == "__main__":
    main()
