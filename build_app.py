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
TODAY = datetime.date.today()   # card "age" is relative to the build, not a frozen date

# --- Cross-device sync (SYNC_DESIGN.md, sync_schema.sql) ---------------------
# Paste these from your Supabase project: Dashboard -> Project Settings -> API.
# The ANON key is public by design and safe to commit — row-level security is what
# protects the data. NEVER put the service_role key here; it bypasses RLS.
# Leaving either empty builds the app with sync switched off.
SUPABASE_URL      = "https://hkonoxawtdsfzjovfdku.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_kiBcVCdAjWI8_CvalphVGg_Iv6BfSFH"


def supabase_lib():
    """The pinned supabase-js UMD bundle, inlined so the app has no external runtime
    dependency and sign-in still works offline. See vendor/README.md."""
    p = os.path.join(HERE, "vendor", "supabase.umd.js")
    if not os.path.exists(p):
        return "/* vendor/supabase.umd.js missing — sync disabled */"
    js = open(p, encoding="utf-8").read()
    return js.replace("</script", "<\\/script")   # defensive; the pinned build has none

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
    data_json = '{"cards":' + payload + ',"sets":' + json.dumps(sets_list).replace("</", "<\\/") + '}'
    build = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    shell = (HTML.replace("__BUILD__", build).replace("__DATE__", date).replace("__N__", str(len(cards))).replace("__FLAG__", str(flagged))
             .replace("__SUPABASE_URL__", SUPABASE_URL).replace("__SUPABASE_KEY__", SUPABASE_ANON_KEY)
             .replace("__RAR__", json.dumps(RARITY_ORDER))
             .replace("__SUPABASE_LIB__", supabase_lib()))
    # file:// cannot fetch, so the desktop build keeps the data inline; the hosted build
    # fetches it, which is what decouples code changes from the payload in git history.
    app_html  = shell.replace("__BOOTSTRAP__", "bootWith(" + data_json + ");")
    docs_html = shell.replace("__BOOTSTRAP__",
        "fetch('cards.json?v=%s').then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);"
        "return r.json();}).then(bootWith).catch(bootFailed);" % build)
    out = os.path.join(HERE, "app.html"); open(out, "w").write(app_html)
    mb = os.path.getsize(out)/1e6
    build = write_pwa(docs_html, build, data_json)
    print(f"snapshot {date} | {len(cards):,} cards | {flagged} gap flags | app.html {mb:.1f} MB")
    print(f"docs/index.html {os.path.getsize(os.path.join(HERE,'docs','index.html'))/1e6:.2f} MB shell"
          f" + cards.json {os.path.getsize(os.path.join(HERE,'docs','cards.json'))/1e6:.1f} MB data")
    print(f"wrote {out} — open it (double-click, or: open app.html). Lists save in the browser.")
    print(f"wrote docs/ (GitHub Pages bundle, sw cache cyberse-{build}) — run publish.command to push it to your phone.")


def write_pwa(html, build, data_json):
    """Emit the hosted bundle for GitHub Pages / the phone PWA into docs/.
    Same page as app.html; card art auto-switches to the CDN when hosted.
    Returns the build id stamped into the service-worker cache name."""
    docs = os.path.join(HERE, "docs")
    os.makedirs(os.path.join(docs, "icons"), exist_ok=True)
    open(os.path.join(docs, "index.html"), "w").write(html)
    open(os.path.join(docs, "cards.json"), "w").write(data_json)
    manifest = {
        "name": "CYBERSE — Yu-Gi-Oh! Hub", "short_name": "CYBERSE",
        "description": "Your personal Yu-Gi-Oh! collection, decks, budget, playtest and meta — all in one place.",
        "start_url": ".", "scope": ".", "display": "standalone", "orientation": "any",
        "background_color": "#070c1c", "theme_color": "#070c1c",
        "icons": [
            {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    open(os.path.join(docs, "manifest.json"), "w").write(json.dumps(manifest, indent=2))
    # Cache-bust per BUILD, not per day: the browser only reinstalls the worker when sw.js itself
    # changes byte-for-byte, so a date-only version made the second rebuild of a day serve the
    # stale page from cache. A timestamp guarantees every publish reaches the phone.
    sw = SW_JS.replace("__BUILD__", build)
    open(os.path.join(docs, "sw.js"), "w").write(sw)
    return build


SW_JS = r"""/* <CYBERSE> service worker — versioned by build timestamp so every publish updates the phone. */
const CACHE='cyberse-__BUILD__';
const CORE=['./index.html','./cards.json','./manifest.json','./icons/icon-192.png','./icons/icon-512.png'];
self.addEventListener('install',function(e){self.skipWaiting();e.waitUntil(caches.open(CACHE).then(function(c){return c.addAll(CORE).catch(function(){});}));});
self.addEventListener('activate',function(e){e.waitUntil(caches.keys().then(function(ks){return Promise.all(ks.map(function(k){return k===CACHE?null:caches.delete(k);}));}).then(function(){return self.clients.claim();}));});
self.addEventListener('fetch',function(e){var req=e.request;if(req.method!=='GET')return;
  if(req.mode==='navigate'){e.respondWith(caches.match('./index.html').then(function(h){return h||fetch(req);}));return;}
  if(new URL(req.url).origin!==location.origin)return; /* let card art (CDN) and fonts hit the network */
  /* ignoreSearch: the page requests cards.json?v=<build> for cache-busting, but the
     precache stores it without a query — an exact match would miss and the installed
     app would fail to load its cards with no network. */
  e.respondWith(caches.match(req,{ignoreSearch:true}).then(function(h){return h||fetch(req).then(function(res){var cp=res.clone();caches.open(CACHE).then(function(c){c.put(req,cp);});return res;});}));
});
"""

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>&lt;CYBERSE&gt; — __DATE__</title>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="#070c1c">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="CYBERSE">
<link rel="manifest" href="manifest.json">
<link rel="icon" href="icons/icon-192.png">
<link rel="apple-touch-icon" href="icons/icon-192.png">
<link rel="preconnect" href="https://images.ygoprodeck.com">
<link rel="preconnect" href="https://fonts.gstatic.com"><link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&display=swap" rel="stylesheet"><style>
:root{--bg:#070c1c;--bg2:#0b1330;--surf:#111d3f;--surf2:#182a55;--line:#2c3d70;--line2:#43598f;
  --ink:#eaf0ff;--mut:#93a0c4;--acc:#8fdcff;--acc2:#5566d8;--pos:#6ee0a0;--warn:#e8c66a;--dang:#ff6b81;
  --gold:#e8c66a;--gold2:#f3dd94;--sh:0 8px 30px rgba(2,6,20,.6);
  /* --hh = header height. Sticky table heads and the board toolbar offset from it, so it MUST
     be re-declared in every breakpoint that changes the header's height. */
  --hh:57px;
  /* iOS safe areas. The head asks for viewport-fit=cover + a translucent status bar, so the
     page really does extend under the notch and the home indicator — these insets are what
     keep content out from under them. Wrapped in custom properties (rather than calling env()
     at each use site) so breakpoints stay readable and the values can be simulated in a
     desktop browser for testing; env() itself always resolves to 0px there.
     Everything below is calc(base + inset), so on any non-notched screen it equals the base
     and the desktop layout is byte-identical to before. */
  --sat:env(safe-area-inset-top,0px);
  --sar:env(safe-area-inset-right,0px);
  --sab:env(safe-area-inset-bottom,0px);
  --sal:env(safe-area-inset-left,0px);
  /* page gutters, re-declared per breakpoint; the insets are added on top of them */
  --bn:0px;                /* bottom navigation height; only mobile has one */
  --hpv:12px;--hph:22px;   /* header  padding vertical / horizontal */
  --cpv:12px;--cph:22px;   /* controls bar */
  --wpt:16px;--wph:22px;   /* .wrap content */
  /* solo-board geometry: side column (field/GY/extra/deck piles) and the gap between zones.
     .bemzrow's padding is derived from these, so shrinking the board is a two-value change. */
  --bside:72px;--bgap:7px}
*{box-sizing:border-box}
/* No zooming at all: `pan-x pan-y` permits scrolling but drops BOTH the double-tap and the
   pinch gestures, so rapid tapping (steppers, life points, board zones) and dragging cards
   never fight the browser. The viewport meta and the gesture handlers below back this up on
   iOS, which ignores parts of each on its own. */
html,body{touch-action:pan-x pan-y}
body{font:13px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;margin:0;color:var(--ink);-webkit-font-smoothing:antialiased;
  background:radial-gradient(1100px 560px at 78% -12%,#161e30 0%,var(--bg) 55%) fixed,var(--bg)}
/* padding-top carries the status-bar/notch inset; the background still bleeds full-width
   under it. --hh is measured from offsetHeight, so the sticky offsets follow automatically. */
header{transition:transform .2s ease;padding:calc(var(--hpv) + var(--sat)) calc(var(--hph) + var(--sar)) var(--hpv) calc(var(--hph) + var(--sal));border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap;position:sticky;top:0;background:rgba(11,15,23,.82);backdrop-filter:blur(12px);z-index:20}
h1{margin:0;font-size:16px;font-weight:700;letter-spacing:-.01em;display:flex;align-items:center;gap:8px}
h1::before{content:"◆";color:var(--acc);font-size:14px}
/* 11 tabs never fit a phone: the strip scrolls sideways instead of overflowing the page.
   Harmless on desktop, where it doesn't overflow in the first place. */
.nav{display:flex;gap:3px;background:var(--surf);padding:3px;border-radius:12px;border:1px solid var(--line);
  max-width:100%;overflow-x:auto;scroll-snap-type:x proximity;-webkit-overflow-scrolling:touch;scrollbar-width:none}
.nav::-webkit-scrollbar{display:none}
.nav .t{padding:6px 15px;border-radius:9px;cursor:pointer;font-size:13px;color:var(--mut);transition:.15s;flex:none;white-space:nowrap;scroll-snap-align:center}
.nav .t:hover{color:var(--ink)} .nav .t.on{background:var(--acc2);color:#fff;font-weight:600}
.kpis{display:flex;gap:8px;margin-left:auto;flex-wrap:wrap}
.kpi{background:var(--surf);border:1px solid var(--line);border-radius:12px;padding:6px 14px;text-align:right;min-width:78px}
.kpi .v{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums}
.kpi.hl{border-color:rgba(87,208,138,.4)}.kpi.hl .v{color:var(--pos)}
.kpi .l{color:var(--mut);font-size:9px;text-transform:uppercase;letter-spacing:.06em;margin-top:1px}
.fltbtn{display:none}
.fltwrap{display:contents}
@media(max-width:900px){
  .fltbtn{display:inline-flex;align-items:center;gap:4px}
  .fltwrap{display:none;width:100%;flex-wrap:wrap;gap:6px}
  .fltwrap.on{display:flex}
}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:var(--cpv) calc(var(--cph) + var(--sar)) var(--cpv) calc(var(--cph) + var(--sal));border-bottom:1px solid var(--line);background:var(--bg2)}
input,select,button{background:var(--surf);color:var(--ink);border:1px solid var(--line2);border-radius:9px;padding:7px 11px;font:inherit;font-size:12px;transition:.15s}
input:focus,select:focus{outline:none;border-color:var(--acc);box-shadow:0 0 0 3px rgba(139,147,255,.16)}
input[type=text]{width:162px}.num{width:66px}
button{cursor:pointer}button:hover{border-color:var(--acc);color:var(--ink);background:var(--surf2)}
label{color:var(--mut);font-size:12px;display:flex;gap:5px;align-items:center}
/* bottom gutter clears the home indicator; 64px base keeps the existing breathing room */
.wrap{padding:var(--wpt) calc(var(--wph) + var(--sar)) calc(64px + var(--sab)) calc(var(--wph) + var(--sal));max-width:1520px}.count{color:var(--mut);margin:4px 0 12px;font-size:12px}
table{border-collapse:separate;border-spacing:0;width:100%}
th,td{padding:8px 11px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mut);font-weight:600;cursor:pointer;font-size:11px;text-transform:uppercase;letter-spacing:.04em;background:var(--bg2)}
#browse th{position:sticky;top:var(--hh);z-index:2}
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
/* --- bottom navigation (mobile) ---
   Five thumb-reachable destinations instead of an eleven-tab strip that had to scroll
   sideways. Everything else lives on Home, which is always one tap away — so nothing got
   further than two taps, and the common destinations got much closer. */
.hdrhide{transform:translateY(-100%)}
/* --- edge drawer --- */
.dgrip{display:none}
.drawer{display:none}
.dscrim{display:none}
@media(max-width:900px){
  .dgrip{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;
    margin-right:2px;border-radius:9px;cursor:pointer;color:var(--gold);font-size:17px;flex:none}
  .dscrim{display:block;position:fixed;inset:0;z-index:44;background:#000;opacity:0;pointer-events:none}
  .drawer{display:flex;flex-direction:column;position:fixed;top:0;bottom:0;left:0;width:284px;z-index:45;
    transform:translateX(-284px);overflow-y:auto;overscroll-behavior:contain;
    padding:calc(var(--sat) + 16px) 12px calc(var(--sab) + 16px);
    background:linear-gradient(180deg,rgba(14,24,56,.99),rgba(9,15,38,.99));
    border-right:1px solid var(--line2);box-shadow:8px 0 34px rgba(2,6,20,.6)}
}
.dhead{padding:4px 8px 14px;border-bottom:1px solid var(--line)}
.dname{font-family:"Cinzel",Georgia,serif;font-size:19px;font-weight:700;color:var(--gold)}
.dsub{font-size:11.5px;color:var(--mut);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dlinks{padding:8px 0;flex:1}
.dlink{display:flex;align-items:center;gap:12px;padding:11px 10px;border-radius:11px;cursor:pointer;
  font-size:14.5px;color:#d7deee;transition:.12s}
.dlink:hover{background:rgba(40,58,110,.4)}
.dlink.on{background:linear-gradient(90deg,rgba(232,198,106,.16),transparent);color:var(--gold2);font-weight:600}
.dico{font-size:17px;width:24px;text-align:center}
.dfoot{padding:10px 10px 0;border-top:1px solid var(--line)}
.bnav{display:none}
.syncdot{width:9px;height:9px;border-radius:50%;background:var(--mut);cursor:pointer;flex:none;
  box-shadow:0 0 0 3px rgba(147,160,196,.12);transition:.15s}
.syncdot.ok{background:var(--pos);box-shadow:0 0 0 3px rgba(110,224,160,.16)}
.syncdot.busy{background:var(--acc);box-shadow:0 0 0 3px rgba(143,220,255,.18)}
.syncdot.warn{background:var(--dang);box-shadow:0 0 0 3px rgba(255,107,129,.18)}
.syncdot.off{background:var(--line2);box-shadow:none}
.vtitle{font-family:"Cinzel",Georgia,serif;font-size:14px;color:var(--gold2);letter-spacing:.01em}
@media(min-width:901px){.vtitle{display:none}}
@media(max-width:900px){
  .nav{display:none}                     /* the scrolling strip is replaced entirely */
  :root{--bn:58px}
  .bnav{display:grid;grid-template-columns:repeat(5,1fr);position:fixed;left:0;right:0;bottom:0;z-index:35;
    padding-bottom:var(--sab);
    background:linear-gradient(180deg,rgba(12,22,52,.94),rgba(8,14,34,.97));
    border-top:1px solid var(--line2);backdrop-filter:blur(14px);
    box-shadow:0 -4px 22px rgba(3,8,24,.5)}
  .bn{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;
    padding:7px 2px 6px;cursor:pointer;color:var(--mut);min-height:52px;transition:.12s;
    border-top:2px solid transparent}
  .bn.on{color:var(--gold);border-top-color:var(--gold)}
  .bni{font-size:17px;line-height:1}
  .bn.on .bni{filter:drop-shadow(0 0 6px rgba(232,198,106,.5))}
  .bnl{font-size:9.5px;letter-spacing:.02em}
  /* content must clear the bar */
  .wrap{padding-bottom:calc(76px + var(--sab))}
  .menuwrap{padding-bottom:calc(80px + var(--sab))}
}
.bootload{position:fixed;inset:0;z-index:70;display:flex;align-items:center;justify-content:center;
  flex-direction:column;text-align:center;padding:24px;color:var(--mut);font-size:13px;
  background:var(--bg)}
.addres{margin:4px 0 12px;display:flex;flex-wrap:wrap;gap:7px}
.ares{display:inline-flex;align-items:center;gap:7px;background:var(--surf);border:1px solid var(--line2);border-radius:20px;padding:5px 13px;cursor:pointer;font-size:12px;transition:.12s}
.ares:hover{border-color:var(--acc);background:rgba(139,147,255,.09)}.ares .nm{font-weight:600}
.ares.addmore{border-color:var(--acc);color:var(--acc);font-weight:600}
.own{color:var(--pos);font-weight:700}
.deckstats{background:linear-gradient(180deg,var(--surf),var(--bg2));border:1px solid var(--line);border-radius:12px;padding:11px 16px;margin:10px 0 6px;font-size:12px}
.sec{font-size:14px;margin:22px 0 8px;color:var(--ink);font-weight:700;letter-spacing:-.01em;display:flex;align-items:center;gap:9px}
.sec::before{content:"";width:3px;height:15px;background:var(--acc);border-radius:2px}
#ov{position:fixed;inset:0;background:rgba(4,6,12,.72);backdrop-filter:blur(5px);display:none;align-items:center;justify-content:center;z-index:40;padding:calc(20px + var(--sat)) calc(20px + var(--sar)) calc(20px + var(--sab)) calc(20px + var(--sal))}
/* The shell does NOT scroll — #mBody inside it does. That's what keeps the close control
   genuinely still: as a sticky element inside the scroller it shifted with the content. */
.modal{position:relative;background:var(--surf);border:1px solid var(--line2);border-radius:18px;
  max-width:600px;width:100%;max-height:88vh;display:flex;flex-direction:column;
  padding:24px 26px;box-shadow:var(--sh)}
#mBody{overflow:auto;min-height:0}
.modal h2{margin:0 0 3px;font-size:21px;letter-spacing:-.01em;padding-right:46px}   /* clears the close */.modal .sub{color:var(--mut);font-size:12px;margin-bottom:12px}
.modal .tx{background:var(--bg2);border:1px solid var(--line);border-radius:11px;padding:12px 15px;font-size:13px;line-height:1.65;white-space:pre-wrap;margin:12px 0}
.modal table{margin:8px 0}
/* The close control was float:right inside .modal — which is the SCROLLING box — so on a tall
   card (many printings) it scrolled off the top and left no way out but tapping the backdrop.
   Sticky keeps it pinned to the top of the modal at any scroll position, and it's now a real
   44px-class target rather than a bare glyph. */
.close{position:absolute;top:10px;right:12px;z-index:5;display:flex;align-items:center;justify-content:center;
  width:38px;height:38px;border-radius:50%;cursor:pointer;
  background:rgba(9,16,40,.92);border:1px solid var(--line2);color:var(--ink);
  font-size:23px;line-height:1;backdrop-filter:blur(6px);transition:.12s}
.close:hover{color:var(--gold2);border-color:var(--gold);background:rgba(232,198,106,.12)}
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
/* background-color UNDER the gradient: the gradient is background-attachment:fixed, so it only
   paints a viewport-sized box. iOS rubber-band overscroll and the home-indicator strip fall
   outside that box and showed white. The solid colour propagates to the viewport canvas and
   covers both. min-height keeps it filling short pages too. */
html{background:linear-gradient(165deg,#0b1636 0%,#070c1c 55%,#05091a 100%) fixed;background-color:#05091a;min-height:100%}
body{background:transparent;min-height:100vh}
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
/* Fixed, not sticky: it only exists while a card is selected, and it must be reachable
   without scrolling back up to wherever the card happened to be. Out of flow, so nothing
   below it shifts when it appears. */
.btoolbar{position:fixed;top:calc(var(--hh) + 8px);left:12px;right:12px;z-index:30;
  max-width:calc(100vw - 16px);box-sizing:border-box;
  display:flex;flex-wrap:wrap;align-items:center;gap:5px;max-height:44vh;overflow-y:auto;
  background:linear-gradient(180deg,rgba(24,38,78,.985),rgba(14,22,50,.985));
  border:1px solid var(--gold);border-radius:11px;padding:9px 11px;margin:0;
  box-shadow:0 10px 34px rgba(2,6,20,.7);backdrop-filter:blur(8px)}
@media(min-width:901px){.btoolbar{width:min(1000px,calc(100vw - 44px))}}
/* NO position:relative here — it would override the position:fixed above at equal
   specificity and drop the toolbar back into the flow, pushing the whole field down.
   position:fixed already establishes the containing block .btx needs. */
.btoolbar .btsel{width:100%;font-size:13px;padding-right:44px}
/* close sits top-right of whichever floating panel is open, as a real 38px target */
.btx{position:absolute;top:6px;right:8px;z-index:2;width:38px;height:38px;display:flex;
  align-items:center;justify-content:center;border-radius:50%;cursor:pointer;font-size:23px;
  line-height:1;color:var(--ink);background:rgba(9,16,40,.9);border:1px solid var(--line2);
  transition:.12s}
.btx:hover{color:var(--gold2);border-color:var(--gold);background:rgba(232,198,106,.14)}
.btoolbar button{font-size:11px;padding:5px 9px}
.btsel{font-weight:700;color:var(--gold2);font-size:12px}
.btsep{width:1px;height:16px;background:var(--line2);margin:0 3px}
.btoolbar button.bon{background:var(--gold);color:#1a1300;border-color:var(--gold);font-weight:700}
.btoolbar button.bprim{background:linear-gradient(180deg,#2c3a6e,#1d2850);border-color:var(--acc);color:var(--ink);font-weight:600}
.btoolbar button.bprim:hover{border-color:var(--gold);color:var(--gold2)}
.bctrl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
.bhint{font-size:11.5px;color:var(--mut);margin:8px 0 2px}
.bfield{display:flex;flex-direction:column;gap:var(--bgap);margin:6px auto 0;max-width:720px;background:radial-gradient(ellipse at 50% 38%,rgba(30,46,96,.35),rgba(8,13,32,.42));border:1px solid var(--line2);border-radius:14px;padding:12px}
/* the EMZ row is inset by exactly one side column so its 5 tracks line up with .bzones below.
   minmax(0,1fr) rather than 1fr: .bslot has an aspect-ratio, so a taller row (e.g. a pile label
   wrapping to two lines) would otherwise raise each track's automatic min-content floor and push
   the tracks wider than the container — which silently knocks the two rows out of alignment. */
/* ONE 7-column grid for every row: side | five zones | side. Previously the side columns
   were a fixed --bside while the zones were fluid, so on a short viewport the sides became
   the tallest thing and dictated row height. Equal fr columns scale together and the rows
   align by construction rather than by a matching calc(). */
/* Seven equal columns. The outer two hold real zones (field spell / graveyard, extra /
   main deck) at the same size as the five in the middle, so no row is taller than another
   and the whole board is centred by construction. */
.bmainrow,.bzrow,.bemzrow,.boppbar{display:grid;
  grid-template-columns:repeat(7,minmax(0,1fr));gap:var(--bgap);align-items:start}
.bzones{display:contents}
.bzrow>.bslot:first-child{grid-column:2}
.bside{min-width:0;display:flex;align-items:flex-start;justify-content:center}
/* explicit columns: phase | EMZ | life points | EMZ | turn — the row was mostly empty */
.bemzoban{grid-column:1}
.bemzphase{grid-column:2}
.bemzrow .bslot:nth-child(3){grid-column:3}
.bemzrow .lpchip{grid-column:4}
.bemzrow .bslot:nth-child(5){grid-column:5}
.bemzturn{grid-column:6}
.bemzban{grid-column:7}
.bemzside{display:flex;align-items:center;justify-content:center;min-width:0}
.bmini2{width:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;
  cursor:pointer;border:1px solid var(--line2);border-radius:9px;padding:4px 2px;
  background:linear-gradient(180deg,rgba(24,38,78,.6),rgba(12,20,46,.66));transition:.12s}
.bmini2:hover{border-color:var(--gold)}
.bmlab{font-size:7px;letter-spacing:.08em;color:var(--mut)}
.bmval{font-family:"Cinzel",Georgia,serif;font-size:14px;font-weight:700;color:var(--gold2);line-height:1.1}
.bmnext{font-size:11px;color:var(--acc);line-height:1}
.phpanel{border-color:var(--acc)}
/* the opponent's 5-wide rows use the same inset as the EMZ so all four rows line up */

.bopp .bslot{border-color:rgba(255,107,129,.34);background:rgba(46,16,28,.28)}
.bopp .bslot.bempty:hover{border-color:var(--dang)}
/* same grid as the rows, so it can never wrap regardless of the field's width */
.boppbar{align-items:end;margin-bottom:2px;padding-bottom:5px;border-bottom:1px dashed rgba(255,107,129,.3)}
.bmybar{margin:3px 0 0;padding:5px 0 0;border-bottom:0;border-top:1px dashed rgba(143,220,255,.3)}
.bmybar .boplab{color:var(--acc)}
.bmybar .bslot{border-color:var(--line2)}
.boppbar .boplab{grid-column:1}
.boppbar .bopfs{grid-column:7;width:auto;margin:0}
.boplab{font-size:9px;text-transform:uppercase;letter-spacing:.07em;color:#ff9aa8;
  align-self:center;margin-right:2px}
/* Zone height follows column width via aspect-ratio, so the only way to make a two-sided
   board fit a short viewport is to cap the field's WIDTH against viewport height. Phones
   are already width-constrained, so this only applies from tablet up. */
/* Applies at every width, not just desktop: on a tablet the field was width-constrained to
   something far taller than the viewport. On phones the width is still the binding limit, so
   this is a no-op there. */
.bfield{max-width:min(720px,calc((100vh - 288px) * 0.76))}
.bopfs{min-width:0}
.bopfs .bslot{width:100%;border-color:rgba(255,107,129,.34)}
/* The opponent's strip is a status row, not a play area — full card-height piles made it
   wrap to two lines and cost more than any actual card row. Short chips instead. */
.bpile.bpc{width:100%}   /* fills its grid cell; a fixed width overflowed the column */
.bpile.bpc .bpcount{font-size:8px}
.boppbar .bptop{aspect-ratio:auto;height:30px}
.boppbar .bpcount{font-size:8px}
.bopfs .bslot{aspect-ratio:auto;height:30px}
.boppbar .bslab{font-size:7.5px}
/* flex-start, not stretch: the side columns must not dictate the row's height. With
   banished stacked over the graveyard that column is twice as tall, and stretch was
   passing that height on to all five zones. */



.bslot{border:1px dashed var(--line2);border-radius:9px;aspect-ratio:59/86;display:flex;align-items:center;justify-content:center;position:relative;cursor:pointer;transition:.12s;background:rgba(12,20,46,.35);overflow:visible}
.bside .bslot{width:100%}
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
.bpile{width:100%;cursor:pointer;text-align:center;position:relative}
.bpile .bptop{aspect-ratio:59/86;border:1px solid var(--line2);border-radius:9px;overflow:hidden;display:flex;align-items:center;justify-content:center;background:rgba(12,20,46,.5)}
.bpile.bempty .bptop{border-style:dashed;background:rgba(12,20,46,.3)}
.bpile:hover .bptop{border-color:var(--acc)}
.bpile .bptop .bcard,.bpile .bptop .bback{width:100%;height:100%}
/* absolute, so a pile is exactly as tall as a zone — as a block above the card it added
   ~20px per row and opened a gap between the monster and spell/trap rows */
.bpcount{position:absolute;top:2px;right:2px;z-index:3;min-width:14px;padding:0 3px;
  border-radius:7px;background:rgba(6,10,26,.86);border:1px solid var(--line2);
  font-size:8.5px;color:#c3ccdb;letter-spacing:.02em;line-height:14px;text-transform:uppercase}
.bhandwrap{margin-top:10px;border:1px solid var(--line2);border-radius:11px;padding:8px 10px;background:linear-gradient(180deg,rgba(24,38,78,.5),rgba(12,20,46,.55))}
.bhlab{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin-bottom:6px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bhhint{color:var(--gold)}
.bhcards{display:flex;flex-wrap:wrap;gap:var(--bgap)}
.bhcards>div{width:var(--bhand,58px);aspect-ratio:59/86;cursor:pointer}
/* --- tap-and-drag --- */
/* touch-action:none only on the cards themselves, so a touch that starts on a card
   drags it instead of scrolling the page; gaps and labels still scroll normally. */
.bslot .bcard,.bhcards .bcard{touch-action:none}
/* A long press on an <img> raises iOS's save/copy callout and the desktop drag-image —
   which is exactly the gesture that now means "pick this card up". Suppress both. */
.bfield,.bhandwrap,.bviewer,.btoolbar,.bpmenu{-webkit-touch-callout:none;-webkit-user-select:none;user-select:none}
.bfield img,.bhandwrap img,.bviewer img{-webkit-touch-callout:none;-webkit-user-drag:none;pointer-events:none}
/* height:auto is load-bearing — .bcard sets height:100%, and on a position:fixed clone that
   resolves against the VIEWPORT, which rendered the drag ghost as a full-height strip. */
.bghost{position:fixed;z-index:60;width:64px;height:auto;pointer-events:none;transform:translate(-50%,-50%) rotate(3deg);
  aspect-ratio:59/86;box-shadow:0 12px 30px rgba(2,6,20,.65);opacity:.92;border-radius:7px;overflow:hidden}
.bghost img{width:100%;height:100%;object-fit:cover;display:block}
.bdim{opacity:.32}
.bheld{transform:scale(1.08);box-shadow:0 0 0 2px var(--gold),0 8px 20px rgba(2,6,20,.6);z-index:5}
.bhot{outline:2px solid var(--gold);outline-offset:1px;background:rgba(232,198,106,.12)!important}
.bpile.bhot .bptop{border-color:var(--gold)}
/* --- Xyz materials --- */
.bmat{position:absolute;left:2px;bottom:2px;z-index:4;min-width:15px;height:15px;padding:0 3px;
  display:flex;align-items:center;justify-content:center;border-radius:8px;
  background:rgba(197,139,255,.94);color:#150a25;font-size:9.5px;font-weight:800;
  box-shadow:0 1px 4px rgba(2,6,20,.6)}
/* --- tokens --- */
.btokc{border-style:dashed}
.btok{width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:3px;padding:3px;text-align:center;background:linear-gradient(160deg,#2b2350,#1a1330)}
.btokn{font-size:8.5px;line-height:1.15;color:#e7dcff;font-weight:700;overflow:hidden;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}
.btoka{font-size:8px;color:var(--gold2);font-variant-numeric:tabular-nums}
.brng{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:9px;
  border:1px solid var(--gold);background:rgba(232,198,106,.14);color:var(--gold2);
  font-weight:700;font-size:12px}
.btokform{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0 2px;
  background:linear-gradient(180deg,rgba(24,38,78,.5),rgba(12,20,46,.55));
  border:1px solid var(--line2);border-radius:12px;padding:11px 13px}
/* --- declared effects --- */
.bfx{position:absolute;right:2px;top:2px;z-index:4;width:14px;height:14px;display:flex;
  align-items:center;justify-content:center;border-radius:50%;background:rgba(232,198,106,.95);
  color:#1a1300;font-size:8px;box-shadow:0 1px 4px rgba(2,6,20,.6)}
/* --- desktop side panels --- */
.bsidepanel{display:none}
.bsidepanel.bsempty{display:none!important}   /* no border/background box when there's nothing to show */
@media(min-width:1200px){
  .bsidepanel{display:block;position:fixed;top:calc(var(--hh) + 14px);width:270px;z-index:8;
    max-height:calc(100vh - var(--hh) - 28px);overflow:auto;padding:12px 14px;border-radius:13px;
    background:linear-gradient(180deg,rgba(20,32,66,.72),rgba(11,18,42,.78));
    border:1px solid var(--line2);box-shadow:0 8px 26px rgba(2,6,20,.45)}
  /* purely informational, so it lets clicks through to the hand underneath rather than
     blocking cards it happens to overlay */
  .bsideleft{left:16px;pointer-events:none}
  .bsideright{right:16px}
}
@media(min-width:1560px){.bsidepanel{width:320px}}
.bsphead{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--gold);margin-bottom:8px}
.bspimg{width:100%;border-radius:9px;margin-bottom:8px;border:1px solid var(--line2)}
.bspname{font-family:"Cinzel",Georgia,serif;font-size:15px;font-weight:700;color:var(--ink);line-height:1.25}
.bspmeta{font-size:11px;color:var(--mut);margin-top:4px}
.bspban{display:inline-block;margin-top:5px;padding:2px 8px;border-radius:20px;font-size:10px;
  font-weight:700;background:rgba(255,107,129,.16);border:1px solid rgba(255,107,129,.4);color:#ff9aa8}
.bsptext{font-size:11.5px;line-height:1.55;color:#c3ccdb;white-space:pre-wrap;margin-top:8px;
  border-top:1px solid var(--line);padding-top:8px}
.bspfx{margin-top:8px;font-size:11.5px;color:var(--gold2)}
.bspgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(58px,1fr));gap:6px}
.bfxlog{margin-top:10px;border:1px solid var(--line2);border-radius:11px;padding:9px 12px;
  background:linear-gradient(180deg,rgba(24,38,78,.42),rgba(12,20,46,.48))}
.bfxrow{font-size:11.5px;color:#c3ccdb;padding:3px 0;border-bottom:1px solid rgba(67,89,143,.25);line-height:1.4}
.bfxrow:last-child{border:0}
.bfxrow b{color:var(--gold2)}
.blogundo{font-size:10px;padding:3px 8px;min-height:24px;margin-left:auto}
.bfxlog .grpchev{transition:transform .18s}
.bfxlog.fold .grpchev{transform:rotate(-90deg)}
.blogpeek{font-size:10.5px;color:#c3ccdb;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  max-width:46%;text-transform:none;letter-spacing:0}
.bctr{position:absolute;left:2px;top:2px;z-index:4;min-width:15px;height:15px;padding:0 3px;
  display:flex;align-items:center;justify-content:center;border-radius:8px;
  background:rgba(110,224,160,.95);color:#052015;font-size:9.5px;font-weight:800}
.bstat{position:absolute;left:0;right:0;bottom:0;z-index:4;padding:1px 0;text-align:center;
  background:rgba(6,10,26,.86);color:var(--gold2);font-size:8px;font-weight:700;
  font-variant-numeric:tabular-nums}
/* --- pile action menu / floating panels --- */
.bpmenu{position:fixed;top:calc(var(--hh) + 8px);left:12px;right:12px;z-index:31;
  max-width:calc(100vw - 16px);box-sizing:border-box;
  display:flex;flex-wrap:wrap;align-items:center;gap:5px;max-height:60vh;overflow-y:auto;
  background:linear-gradient(180deg,rgba(24,38,78,.985),rgba(14,22,50,.985));
  border:1px solid var(--acc);border-radius:11px;padding:9px 11px;
  box-shadow:0 10px 34px rgba(2,6,20,.7);backdrop-filter:blur(8px)}
.bpmenu button{font-size:11px;padding:7px 10px;min-height:34px}
.bpmenu .btsel{width:100%;font-size:13px;color:var(--acc)}
@media(min-width:901px){.bpmenu{width:min(900px,calc(100vw - 44px))}}
.lppanel{border-color:var(--gold)}
.lppanel .lpside{flex:1 1 190px}
/* --- turn phases --- */
.bph{font-size:11px;padding:5px 9px;min-height:30px;min-width:38px;color:var(--mut)}
.bph.on{background:linear-gradient(180deg,#26315f,#1a2247);color:var(--gold);font-weight:700;
  border-color:var(--gold);box-shadow:0 0 10px rgba(232,198,106,.22)}
.bphnext{font-size:13px;padding:5px 10px;min-height:30px}
/* --- life points --- */
/* the chip sits in the EMZ row's empty middle column */
.lpchip{display:flex;overflow:hidden;flex-direction:column;align-items:center;justify-content:center;
  gap:1px;cursor:pointer;border:1px solid var(--line2);border-radius:9px;
  background:linear-gradient(180deg,rgba(24,38,78,.72),rgba(12,20,46,.78));padding:2px}
/* clamped and clipped: at narrow column widths the totals used to overflow the chip and
   paint across the EMZ slots either side, which read as the EMZ being mispositioned */
.lpcv{font-family:"Cinzel",Georgia,serif;font-size:clamp(8px,2.6vw,12px);font-weight:700;
  color:var(--gold2);font-variant-numeric:tabular-nums;line-height:1.15;
  max-width:100%;overflow:hidden;text-overflow:clip;white-space:nowrap}
.lpcv.lpco{color:#ff9aa8}
.lpcs{font-size:7.5px;letter-spacing:.08em;color:var(--mut)}
.lpside{flex:1 1 200px;min-width:0;background:linear-gradient(180deg,rgba(24,38,78,.55),rgba(12,20,46,.6));
  border:1px solid var(--line2);border-radius:12px;padding:9px 11px}
.lpside.lpout{border-color:var(--dang);box-shadow:inset 0 0 0 1px rgba(255,107,129,.35)}
.lplab{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--mut)}
.lpval{font-family:"Cinzel",Georgia,serif;font-size:26px;font-weight:700;color:var(--gold2);
  line-height:1.1;font-variant-numeric:tabular-nums}
.lpout .lpval{color:var(--dang)}
.lpq{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}
.lpq button{font-size:11px;padding:5px 8px;min-height:30px}
.lpin{width:82px;font-size:12px;padding:5px 8px;text-align:right}
.lpmeta{display:flex;flex-direction:column;gap:5px;justify-content:center;align-items:flex-start}
.lpmeta button{font-size:11px;padding:5px 9px;min-height:30px}
.bviewer{position:fixed;inset:0;background:rgba(4,8,20,.72);z-index:50;display:flex;align-items:center;justify-content:center;padding:calc(20px + var(--sat)) calc(20px + var(--sar)) calc(20px + var(--sab)) calc(20px + var(--sal))}
.bvbox{background:linear-gradient(180deg,#141f42,#0c1430);border:1px solid var(--gold);border-radius:14px;max-width:840px;width:100%;max-height:82vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(2,6,20,.7)}
.bvhead{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid var(--line2)}
.bvcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:9px;padding:14px;overflow:auto}
.bvcard{aspect-ratio:59/86;border-radius:7px;overflow:hidden;position:relative;cursor:pointer;border:1px solid var(--line2);background:linear-gradient(160deg,#1a2547,#0e1730);transition:.1s}
.bvcard:hover{border-color:var(--gold);transform:translateY(-2px)}
.bvfdc{border-color:var(--gold);border-style:dashed}
.bvfdc img{opacity:.45;filter:grayscale(.5)}
.bvfd{position:absolute;left:0;right:0;bottom:0;z-index:3;padding:2px 0;text-align:center;
  background:rgba(232,198,106,.92);color:#1a1300;font-size:8px;font-weight:800;
  text-transform:uppercase;letter-spacing:.04em}
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
/* Tables keep white-space:nowrap for readability, so on narrow screens they scroll inside
   their own box rather than dragging the whole page sideways. NOTE: an overflow container
   is also a scroll container, which kills position:sticky on <th> — so this only engages
   below 900px, and sticky headers are explicitly turned off there. */
.tscroll{max-width:100%}
/* ============================================================================
   RESPONSIVE LAYER — everything below only applies to narrow screens.
   Desktop (>=901px) renders exactly as it did before this block existed.
   ============================================================================ */
/* Browse has 11 nowrap columns and needs ~1330px. Between the scroller breakpoint and that
   width the page itself scrolled sideways. Dropping the two least-consulted columns closes
   the gap without a scroll container, which is what would have cost the sticky header. */
@media(max-width:1340px){
  #browse th:nth-child(4),#browse td:nth-child(4),   /* Archetype */
  #browse th:nth-child(6),#browse td:nth-child(6){display:none}   /* Age */
}
/* Below ~1000px even the trimmed table cannot fit, so the scroll container takes over a
   little earlier than the phone breakpoint. Sticky heads go with it — an overflow container
   is also a scroll container — but that band is tablet width, where the fixed header matters
   less than not dragging the whole page sideways. */
/* On a phone the table kept Card and Ban and pushed the price off-screen behind a
   sideways scroll. Show what you actually came for — name, how many you own, price — and
   let it fit outright. Everything else is in the card popup. */
@media(max-width:640px){
  #browse th:nth-child(2),#browse td:nth-child(2),
  #browse th:nth-child(3),#browse td:nth-child(3),
  #browse th:nth-child(4),#browse td:nth-child(4),
  #browse th:nth-child(5),#browse td:nth-child(5),
  #browse th:nth-child(6),#browse td:nth-child(6),
  #browse th:nth-child(9),#browse td:nth-child(9),
  #browse th:nth-child(10),#browse td:nth-child(10){display:none}
  /* the name is the only column that can give: let it wrap so the table compresses to the
     screen. The scroller stays as a safety net rather than overflowing the page. */
  #browse td:nth-child(1){white-space:normal;min-width:110px;line-height:1.3}
  #browse .tscroll table{min-width:0}
  #browse .addb{padding:2px 6px;margin-left:2px}
}
@media(max-width:1000px){
  .tscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
  .tscroll table{min-width:660px}
  #browse th{position:static}
}
@media(max-width:1150px){
  #browse th:nth-child(2),#browse td:nth-child(2),    /* Class */
  #browse th:nth-child(10),#browse td:nth-child(10){display:none}   /* Gap x */
}
@media(max-width:900px){
  .tscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
  .tscroll table{min-width:660px}
  #browse th{position:static}          /* can't stay sticky inside a scroll container */
  /* set the gutter variables rather than the padding shorthand — a shorthand here would
     overwrite the safe-area insets baked into the base rules */
  :root{--hpv:10px;--hph:14px;--cpv:10px;--cph:14px;--wpt:14px;--wph:14px}
  /* two deterministic rows (title + KPIs, then the tab strip) instead of the desktop header
     wrapping into three — the nav scrolls, so it always occupies exactly one row */
  header{gap:10px;flex-wrap:wrap;row-gap:8px}
  h1{order:1;flex:none}
  .kpis{order:2;margin-left:auto}
  .nav{order:3;width:100%}
}
@media(max-width:640px){
  /* header becomes two rows: title + KPIs, then the tab strip. Its real height is measured
     into --hh at runtime by syncHH(), so nothing here has to be kept in sync by hand. */
  :root{--bside:46px;--bgap:3px;--bhand:38px;
        --hpv:8px;--hph:10px;--cpv:10px;--cph:12px;--wpt:12px;--wph:12px}
  header{gap:8px}
  h1{font-size:15px;order:1}
  /* explicit order: the title and sync dot default to 0 and were rendering before the logo */
  .vtitle{order:2;font-size:12.5px;color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .vtitle::before{content:"/ ";opacity:.5}
  .syncdot{order:3}
  .kpis{order:4}
  /* The bordered tiles cost ~24px of chrome each and were clipping their own figures.
     Plain text with a tiny caption reads at a glance and fits; the full set is on Home. */
  /* Two figures, as plain text. The old rules here laid them out as a FOUR-column grid with
     overflow:hidden — so the two survivors each got a quarter of the width and were clipped,
     which is what made them unreadable. Nothing here constrains their width now. */
  .kpi:nth-child(2),.kpi:nth-child(4){display:none}
  .kpis{display:flex!important;gap:14px;align-items:baseline;flex:0 0 auto;min-width:0;
    margin-left:auto;grid-template-columns:none!important}
  .kpi{border:0!important;background:none!important;box-shadow:none!important;padding:0!important;
    min-width:0;overflow:visible!important;text-align:right;display:flex;align-items:baseline;gap:5px;
    white-space:nowrap}
  .kpi .v{font-size:14px!important;white-space:nowrap}
  .kpi .l{font-size:8.5px!important;margin:0;opacity:.75;letter-spacing:.04em}
  /* grid tracks shrink instead of wrapping, so the KPI row can never overflow the header
     or push it onto a third line */
  .nav{order:3;width:100%;border-radius:10px}
  .nav .t{padding:7px 13px;font-size:13px}
  .controls{gap:6px}
  .controls input[type=text]{width:100%;min-width:0;flex:1 1 100%}
  .controls .num{width:70px}
  .tscroll table{min-width:600px}
  th,td{padding:7px 9px}
  /* modals: the desktop padding wastes a third of a phone screen */
  #ov{padding:calc(10px + var(--sat)) calc(10px + var(--sar)) calc(10px + var(--sab)) calc(10px + var(--sal))}
  .modal{padding:16px 15px;max-height:92vh;border-radius:14px}
  .close{width:44px;height:44px;font-size:26px;top:8px;right:8px}   /* full thumb target */
  .modal h2{font-size:18px}
  .cimg{width:104px;margin:0 0 10px 12px}
  .rsets{max-width:none}
  /* ---- solo board: scale the field, never stack it (the spatial layout IS the feature) ----
     With the opponent's side in play the board is twice as tall, so the phone squeezes the
     zones inward: the side padding narrows all five columns proportionally. */
  /* tighten via --bgap, never by overriding `gap` directly: .bzrow/.bemzrow derive their
     inset from calc(--bside + --bgap), so a raw gap override desynchronises the rows. */
  /* 5 columns make each zone wider (and so taller) than the 7-column layout, so the
     height cap needs a smaller ratio here. The board ends up narrower than the screen and
     centred, which is fine — it's still bigger cards than the 7-column version gave. */
  .bfield{padding:6px 0;border-radius:11px;margin-left:auto;margin-right:auto;
    max-width:min(100%,calc((100vh - 352px) * 0.72))}   /* 344 accounts for the bottom bar */
  .boppbar .boplab{font-size:7px}
  .boppbar{padding-bottom:4px}
  .boplab{font-size:8px}
  .bviewer{padding:10px}
  .bvbox{max-height:90vh;border-radius:12px}
  .bvcards{grid-template-columns:repeat(auto-fill,minmax(62px,1fr));gap:6px;padding:10px}
  .bslab{font-size:8px}
  /* pile captions wrap to two lines in a 40px column; reserve the same height for every pile
     so the board's rows stay level with each other */
  .bpcount{font-size:8px;line-height:1.15;min-height:2.1em;display:flex;align-items:flex-end;justify-content:center}
  /* the toolbar is the board's primary control surface — give it real tap targets */
  .btoolbar{padding:7px 8px;gap:4px;border-radius:9px}
  .btoolbar button{font-size:11px;padding:7px 10px;min-height:34px}
  .bctrl button,.bctrl select{min-height:34px}
  /* charts and label columns sized for a desktop gutter */
  .clab{width:120px;font-size:11px}
  .cval{width:88px;font-size:11px}
  .wrlab{width:104px}
  .wrval{width:92px;font-size:11px}
  .impnm{width:118px}
  .cblab{width:88px}
  .cbspent{width:74px}
  .simcard{width:78px}
  .oddscard{min-width:0;flex:1 1 44%;padding:10px 12px}
  .oddspct{font-size:20px}
  .menuwrap{padding:34px 14px 70px}
  .mitem{padding:13px 14px;gap:12px}
  .mitem:hover{transform:none}   /* no hover on touch; the shift just looks like a glitch */
  .mt{font-size:16px}
  .md{font-size:11.5px}
  .mic{font-size:21px;width:30px}
  .savebar{gap:14px}
}
/* On a narrow phone the grip, name, title, dot and two figures wrap to a second row. The
   bottom bar already highlights where you are, so the title is the redundant one. */
@media(max-width:440px){.vtitle{display:none}}
@media(max-width:400px){
  :root{--bside:40px;--bhand:40px}
  .nav .t{padding:7px 11px}
}
</style></head><body><canvas id="bg"></canvas><div id="aura"></div>
<header><span class=dgrip id=dgrip onclick="drawerOpen()" title="menu">&#9776;</span><h1 onclick="go('menu')" style="cursor:pointer" title="main menu">&lt;CYBERSE&gt;</h1>
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
<span class=syncdot id=syncdot title="sync status" onclick="go('you')"></span>
<div class=vtitle id=vtitle></div>
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
  <button class=fltbtn id=fltbtn onclick="toggleFilters()">&#9662; Filters</button>
  <div class=fltwrap id=fltwrap>
  <input type="text" id="qa" placeholder="archetype…" oninput="rB()">
  <select id="rar" onchange="rB()"></select>
  <select id="cl" onchange="rB()"><option value="">class: all</option><option>Monster</option><option>Spell</option><option>Trap</option></select>
  <select id="bn" onchange="rB()"><option value="">ban: all</option><option>Unlimited</option><option>Semi-Limited</option><option>Limited</option><option>Forbidden</option></select>
  <label>$ min <input class="num" inputmode=decimal id="pmin" oninput="rB()"></label>
  <label>$ max <input class="num" inputmode=decimal id="pmax" oninput="rB()"></label>
  <label><input type="checkbox" id="deal" onchange="rB()"> gap deals</label>
  </div>
</div>
<div class="wrap"><div class="count" id="cnt"></div>
<div class="tscroll"><table><thead><tr>
<th onclick="S('n')">Card</th><th onclick="S('cl')">Class</th><th onclick="S('bn')">Ban</th>
<th onclick="S('ar')">Archetype</th><th onclick="S('hr')">Top rarity</th><th class="r" onclick="S('ag')">Age</th>
<th class="r" onclick="S('own')" title="how many you own">Own</th>
<th class="r" onclick="S('m')">Market $</th><th class="r rar" id="ph" onclick="S('rarity')">Rarity $</th>
<th class="r" onclick="S('gap')">Gap×</th><th>Add</th></tr></thead><tbody id="tb"></tbody></table></div></div>
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
<div id="you" class="hide"><div class="wrap" id="youBody"></div></div>
<div id="meta" class="hide"><div class="wrap" id="metaBody"></div><input id="metaFile" type="file" accept=".ydk,.txt" multiple class="hide" onchange="metaImport(event)"></div>

<div class=dscrim id=dscrim onclick="drawerClose()"></div>
<aside class=drawer id=drawer>
  <div class=dhead>
    <div class=dname>&lt;CYBERSE&gt;</div>
    <div class=dsub id=dsub>Not signed in</div>
  </div>
  <div class=dlinks id=dlinks></div>
  <div class=dfoot id=dfoot></div>
</aside>
<nav class=bnav id=bnav>
  <div class="bn" data-v="menu" onclick="go('menu')"><span class=bni>&#9670;</span><span class=bnl>Home</span></div>
  <div class="bn" data-v="browse" onclick="go('browse')"><span class=bni>&#128269;</span><span class=bnl>Browse</span></div>
  <div class="bn" data-v="deck" onclick="go('deck')"><span class=bni>&#127183;</span><span class=bnl>Decks</span></div>
  <div class="bn" data-v="collection" onclick="go('collection')"><span class=bni>&#128230;</span><span class=bnl>Collection</span></div>
  <div class="bn" data-v="sim" onclick="go('sim')"><span class=bni>&#127922;</span><span class=bnl>Play</span></div>
</nav>
<div id="loading" class=bootload>Loading card data&hellip;</div>
<div id="ov" onclick="if(event.target.id==='ov')closeM()"><div class="modal"><span class=close onclick="closeM()" title="close">&times;</span><div id="mBody"></div></div></div>

<script>
/* Card data arrives via the bootstrap block at the end of this script. On the hosted build that's
   a fetch of cards.json, so the page shell and the ~13MB payload version independently — a
   code change no longer rewrites the blob, which is what was inflating the repo. The file://
   build still inlines it, because fetch() cannot read file URLs. */
var CARDS=[], SETS=[], RAR=__RAR__, ORD={}; RAR.forEach(function(r,i){ORD[r]=i;});
var BY={};
/* Card art: use the local 2.3GB cache when opened as a file on the desktop;
   pull from YGOPRODeck's CDN when the app is hosted (phone / GitHub Pages). */
var IMGBASE=(location.protocol==='file:')?'data/images/':'https://images.ygoprodeck.com/images/cards/';
function imgSrc(id){return IMGBASE+id+'.jpg';}
var PRICED=[], NAME2ID={};
var KEY="ygo_builder_v1", view="browse", sk="m", sd=-1, LIMIT=250;
var St=null;
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
  if(!s.settings)s.settings={};
  return s;}
/* Every mutation funnels through here (33 call sites), so it's also the one place
   sync needs to hook. syncTouch is defined in the sync block below; guarded so the
   app is unaffected when sync is off (file://, or no Supabase config). */
function sv(){localStorage.setItem(KEY,JSON.stringify(St)); if(window.syncTouch)window.syncTouch();}
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

var VIEW_TITLE={menu:'',you:'Profile',browse:'Browse',deck:'Decks',collection:'Collection',wishlist:'Wishlist',
  bank:'Bank',sim:'Playtest',plog:'Match log',sets:'Sets',meta:'Meta',analytics:'Analytics'};
function go(v){view=v;if(window.listReset)listReset();
  if(window.showHeader)window.showHeader();
  /* the bottom bar carries five destinations; anything else leaves it unhighlighted and is
     reached from Home, which keeps the bar honest about where you are */
  document.querySelectorAll('.bnav .bn').forEach(function(t){t.classList.toggle('on',t.dataset.v===v);});
  var vt=document.getElementById('vtitle');
  if(vt){vt.textContent=VIEW_TITLE[v]||''; vt.classList.toggle('hide',!VIEW_TITLE[v]);}
  document.querySelectorAll('.nav .t').forEach(function(t){var on=t.dataset.v===v;t.classList.toggle('on',on);
    /* keep the active tab visible in the scrolling strip on narrow screens.
       block:'nearest' so this never yanks the page vertically. */
    if(on&&t.scrollIntoView)try{t.scrollIntoView({inline:'center',block:'nearest'});}catch(e){}});
  document.getElementById('menu').classList.toggle('hide',v!=='menu');
  document.getElementById('browse').classList.toggle('hide',v!=='browse');
  document.getElementById('analytics').classList.toggle('hide',v!=='analytics');
  document.getElementById('bank').classList.toggle('hide',v!=='bank');
  document.getElementById('sim').classList.toggle('hide',v!=='sim');
  document.getElementById('plog').classList.toggle('hide',v!=='plog');
  document.getElementById('sets').classList.toggle('hide',v!=='sets');
  document.getElementById('meta').classList.toggle('hide',v!=='meta');
  document.getElementById('you').classList.toggle('hide',v!=='you');
  document.getElementById('list').classList.toggle('hide',!(v==='deck'||v==='collection'||v==='wishlist'));
  if(v==='menu'){rMenu();return;}
  if(v==='browse'){rB();return;}
  if(v==='analytics'){rA();return;}
  if(v==='bank'){renderBank();return;}
  if(v==='sim'){renderSim();return;}
  if(v==='plog'){renderLog();return;}
  if(v==='sets'){renderSets();return;}
  if(v==='meta'){renderMeta();return;}
  if(v==='you'){renderYou();return;}
  var ctrl='';
  if(v==='deck'){ctrl+='<select onchange="pickDeck(this.value)">'+Object.keys(St.decks).map(function(n){return '<option'+(n===St.active?' selected':'')+'>'+esc(n)+'</option>';}).join('')+'</select>'
    +'<button onclick="newDeck()">+ New deck</button><button onclick="renDeck()">Rename</button><button onclick="delDeck()">Delete</button>';}
  ctrl+='<input type="text" id="lq" placeholder="filter this '+v+'…" oninput="listReset();rTable()">';
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
var ADD_PAGE=24, addShown=ADD_PAGE, addQ='';
function addSearch(){var el=document.getElementById('addq'),box=document.getElementById('addres'); if(!el||!box)return;
  var vq=el.value.toLowerCase();
  if(vq!==addQ){addQ=vq;addShown=ADD_PAGE;}          /* a new query starts from the first page */
  if(vq.length<2){box.innerHTML='';return;}
  /* match everything, then page through it — the old cap of 8 silently hid the rest with
     no way to reach it */
  var hits=[];for(var i=0;i<CARDS.length;i++){if(CARDS[i].n.toLowerCase().indexOf(vq)>=0)hits.push(CARDS[i]);}
  var shown=Math.min(hits.length,addShown), more=hits.length-shown;
  box.innerHTML=hits.slice(0,shown).map(function(c){var own=ownQ(c.i)?' · own '+ownQ(c.i):'';
    var fn=view==='deck'?'addToDeck('+c.i+')':'add(\''+view+'\','+c.i+')';
    return '<span class=ares onclick="'+fn+'"><span class=nm>'+esc(c.n)+'</span><span class=mut> '+(c.m==null?'':'$'+c.m.toFixed(2))+own+'</span> <span class=addb>+'+view+'</span></span>';}).join('')
    +(more?'<span class="ares addmore" onclick="addMore()">▾ '+Math.min(more,ADD_PAGE)+' more <span class=mut>('+hits.length+' matches)</span></span>'
           :(hits.length>ADD_PAGE?'<span class=mut style="font-size:11px;align-self:center">all '+hits.length+' shown</span>':''));}
function addMore(){addShown+=ADD_PAGE;addSearch();}

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
function narrowNav(){return window.matchMedia&&window.matchMedia('(max-width:900px)').matches;}
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
  IT.you=['\u2699\uFE0F','Profile &amp; settings','Sync, backups, board defaults'];
  /* With a bottom bar, Browse / Decks / Collection / Play are already one tap away — leading
     Home with them again would just be a second copy of the same navigation. On phones Home
     becomes the place for everything that ISN'T in the bar. */
  var groups = narrowNav()
    ? [['Collect','the rest of your collection',['wishlist','bank']],
       ['Play &amp; track','log how your decks actually do',['plog']],
       ['Market &amp; meta','scout sets, the metagame &amp; the market',['sets','meta','analytics']],
       ['You','account, data &amp; defaults',['you']]]
    : [['Cards &amp; decks','the everyday hub — find, build, track',['browse','deck','collection','wishlist']],
       ['Play &amp; track','test a deck, then log how it does',['sim','plog']],
       ['Market &amp; meta','scout sets, the metagame &amp; the market',['sets','meta','analytics']],
       ['Budget','money in &amp; out of the hobby',['bank']],
       ['You','account, data &amp; defaults',['you']]];
  var intro=localStorage.getItem('ygo_seen')?'':'<div class=qstart><span class=qx onclick="dismissIntro()" title="dismiss">✕</span>'
    +'<div class=qh>New here? Start simple.</div><div class=qp>&lt;CYBERSE&gt; grows with you — you don’t need all of it at once. '
    +'Begin in <b>Cards &amp; decks</b>: browse cards and build a deck. Everything else — playtest odds, match log, sets, meta, budget — '
    +'is here when you want it, and it all saves automatically in your browser.</div></div>';
  var html=intro+groups.map(function(g){return '<div class=mgh>'+g[0]+' <span class=mgs>'+g[1]+'</span></div>'
    +g[2].map(function(k){var i=IT[k];return '<div class=mitem onclick="go(\''+k+'\')"><div class=mic>'+i[0]+'</div><div><div class=mt>'+i[1]+'</div><div class=md>'+i[2]+'</div></div><div class=marrow>▸</div></div>';}).join('');}).join('');
  document.getElementById('menugrid').innerHTML=html;
  document.getElementById('savebar').innerHTML='<span>Snapshot <b>__DATE__</b></span><span>Collection <b>$'+lt('collection').toFixed(2)+'</b></span><span>Decks <b>'+dN+'</b></span><span>Wishlist <b>'+wN+'</b></span>'
    +(window.syncChip?window.syncChip():'')+'<span class=qlink onclick="showIntro()">▸ quick start</span>'
    +'<span class=mut style="font-size:10px" title="build __BUILD__ — check this matches after publishing">build __BUILD__</span>';}

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
    +'<label class=mut style="font-size:12px">Budget $ <input class=num inputmode=decimal id=bkBud value="'+(bud||'')+'" onchange="setBudget(this.value)"></label></div>';
  // ---- 1. Log a transaction ----
  var logBody='<div class=bform>'
    +'<input type=date id=bkDate value="'+new Date().toISOString().slice(0,10)+'">'
    +'<select id=bkDir onchange="renderBankCats()"><option value=out>Spend</option><option value=in>Income</option></select>'
    +'<select id=bkCat></select><input class=num inputmode=decimal id=bkAmt placeholder="amount">'
    +'<input type=text id=bkNote placeholder="note (optional)" style="flex:1;min-width:140px">'
    +'<button onclick="bankAdd()">+ Log</button></div>';
  h+=grp('log','Log a transaction',null,logBody);
  // ---- 2. Ledger (with inline edit) ----
  var lb='<div class=bform>'
    +'<label class=mut>Month <select onchange="bkFMonth=this.value;renderBank()"><option value=all'+(bkFMonth==='all'?' selected':'')+'>all</option>'+months.map(function(m){return '<option value="'+m+'"'+(bkFMonth===m?' selected':'')+'>'+mName(m)+'</option>';}).join('')+'</select></label>'
    +'<label class=mut>Category <select onchange="bkFCat=this.value;renderBank()"><option value=all'+(bkFCat==='all'?' selected':'')+'>all</option>'+cats.map(function(c){return '<option'+(bkFCat===c?' selected':'')+'>'+esc(c)+'</option>';}).join('')+'</select></label></div>';
  if(!ftx.length)lb+='<div class=empty>'+(tx.length?'No transactions match the filter.':'No transactions yet — log one above.')+'</div>';
  else lb+='<div class=tscroll><table><tr><th>Date</th><th>Type</th><th>Category</th><th class=r>Amount</th><th>Note</th><th></th></tr>'+ftx.map(function(t){var col=t.dir==='out'?RED:'var(--pos)';
    if(t.id===bkEditId)return '<tr class=edrow><td><input type=date id=edDate value="'+t.date+'"></td>'
      +'<td><select id=edDir onchange="renderBankEditCats()"><option value=out'+(t.dir==='out'?' selected':'')+'>Spend</option><option value=in'+(t.dir==='in'?' selected':'')+'>Income</option></select></td>'
      +'<td><select id=edCat>'+bankCats(t.dir).map(function(c){return '<option'+(c===t.cat?' selected':'')+'>'+esc(c)+'</option>';}).join('')+'</select></td>'
      +'<td class=r><input class=num inputmode=decimal id=edAmt value="'+t.amt+'"></td>'
      +'<td><input type=text id=edNote value="'+eatt(t.note)+'"></td>'
      +'<td style="white-space:nowrap"><span class=addb onclick="bankSave('+t.id+')">Save</span><span class=x onclick="bankCancel()">✕</span></td></tr>';
    return '<tr><td>'+t.date+'</td><td style="color:'+col+'">'+(t.dir==='out'?'Spend':'Income')+'</td><td>'+esc(t.cat)+'</td><td class="r" style="color:'+col+'">'+(t.dir==='out'?'−':'+')+'$'+t.amt.toFixed(2)+'</td><td class=mut>'+esc(t.note||'')+'</td><td style="white-space:nowrap"><span class=addb onclick="bankEdit('+t.id+')" title="edit">✎</span><span class=x onclick="bankDel('+t.id+')" title="delete">✕</span></td></tr>';}).join('')+'</table></div>';
  h+=grp('ledger','Ledger',tx.length?ftx.length+' of '+tx.length+' shown':null,lb);
  // ---- 3. Category budgets ----
  var cb=St.bank.catBudgets||{},mByCat={};
  tx.forEach(function(t){if(t.dir==='out'&&ym(t.date)===now)mByCat[t.cat]=(mByCat[t.cat]||0)+t.amt;});
  var capTot=CATS_OUT.reduce(function(s,c){return s+(cb[c]||0);},0);
  var budBody='<div class=catbud>'
    +CATS_OUT.map(function(c){var sp=mByCat[c]||0,bg=cb[c]||0,p=bg>0?Math.min(100,100*sp/bg):0,ov=bg>0&&sp>bg;
      return '<div class=cbrow><div class=cblab>'+esc(c)+'</div><div class=cbbarwrap><div class=cbbar style="width:'+p.toFixed(0)+'%;'+(ov?'background:'+RED:'')+'"></div></div><div class=cbspent'+(ov?' style="color:'+RED+'"':'')+'>$'+sp.toFixed(0)+(bg>0?' / $'+bg.toFixed(0):'')+'</div><input class="num cbinp" inputmode=decimal value="'+(bg||'')+'" placeholder="cap" onchange="setCatBudget(\''+c+'\',this.value)"></div>';}).join('')+'</div>'
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
    :'<div class=tscroll><table><tr><th>Month</th><th class=r>Earned</th><th class=r>Spent</th><th class=r>Net</th></tr>'+months.map(function(k){var mo=byMonth[k],net=mo.i-mo.o;
    return '<tr><td>'+mName(k)+'</td><td class="r" style="color:var(--pos)">$'+mo.i.toFixed(2)+'</td><td class="r" style="color:'+RED+'">$'+mo.o.toFixed(2)+'</td><td class="r" style="color:'+(net>=0?'var(--pos)':RED)+'">'+(net>=0?'+':'−')+'$'+Math.abs(net).toFixed(2)+'</td></tr>';}).join('')+'</table></div>';
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
        return '<div class="simcard'+(extra?' drawn':'')+'" onclick="openM('+id+')"><img src="'+imgSrc(id)+'" onerror="this.style.display=\'none\'"><div class=simnm>'+esc(c?c.n:''+id)+'</div>'+(tg.length?'<div class=simtags>'+tg.map(function(t){return '<span class=simtag title="'+tagLabel(t)+'" style="background:'+tagColor(t)+'"></span>';}).join('')+'</div>':'')+'</div>';};
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
    +comboDraft.reqs.map(function(r,i){return '<div class=comboreq><span class=mut style="font-size:11px">need</span><input class=cnum type=number inputmode=numeric min=1 value="'+(r.count||1)+'" onchange="comboReqCount('+i+',this.value)"><select onchange="comboReqSel('+i+',this.value)">'+selOptions(r.sel)+'</select><span class=x onclick="comboDelReq('+i+')">✕</span></div>';}).join('')
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
    :'<div class=mut style="font-size:11px;margin-bottom:8px">Tap tags to toggle (a card can have several). “Draws” = how many extra cards you see when you activate it (draw/dig spells) — used by the odds simulation. Tags are remembered per card across decks.</div><div class=tscroll><table><tr><th>Card</th><th>Qty</th><th>Tags</th><th>Draws</th></tr>'+uniq.map(function(u){var c=BY[u.id];
      return '<tr><td class=nm onclick="openM('+u.id+')">'+esc(c?c.n:''+u.id)+'</td><td>'+u.q+'</td><td style="white-space:normal"><div class=tchips>'+TAGS.map(function(T){var on=cardTags(u.id).indexOf(T[0])>=0;return '<span class="tchip'+(on?' on':'')+'"'+(on?' style="background:'+T[2]+';border-color:'+T[2]+';color:#0b1330"':'')+' onclick="toggleTag('+u.id+',\''+T[0]+'\')">'+T[1]+'</span>';}).join('')+'</div></td><td><input class=cnum type=number inputmode=numeric min=0 value="'+(St.draws[u.id]||'')+'" placeholder="0" onchange="setDraws('+u.id+',this.value)"></td></tr>';}).join('')+'</table></div>';
  h+=grp('sroles','Card roles &amp; tags',uniq.length+' cards',rolesBody);
  document.getElementById('simBody').innerHTML=h;}

/* ===== Solo playtest board (DuelingBook-like: interactable piles + proper field) ===== */
var board=null, sel=null, placeMode='atk', viewer=null, dragJustEnded=false;
/* Where the last tap landed, so a panel can open next to your finger instead of making you
   travel to a fixed spot at the top of the screen. */
var lastPt=null;
addEventListener('pointerdown',function(e){lastPt={x:e.clientX,y:e.clientY};},{passive:true,capture:true});
/* The anchor is captured when a panel first appears and reused until every panel closes —
   otherwise pressing a button inside it re-anchored to that button and the panel walked
   across the screen as you worked. */
var panelAnchor=null;
function placePanels(){
  var els=['.btoolbar','.bpmenu'].map(function(q){return document.querySelector(q);}).filter(Boolean);
  if(!els.length){panelAnchor=null;return;}
  if(!panelAnchor)panelAnchor=lastPt||{x:innerWidth/2,y:innerHeight/3};
  var pad=8, hh=parseInt(getComputedStyle(document.documentElement).getPropertyValue('--hh'))||60;
  els.forEach(function(el){
    el.style.left='0px'; el.style.top='0px'; el.style.right='auto'; el.style.transform='none';
    var w=Math.min(el.offsetWidth, innerWidth-pad*2), h=el.offsetHeight;
    var x=Math.min(Math.max(pad,panelAnchor.x-w/2), Math.max(pad,innerWidth-w-pad));
    var y=panelAnchor.y+18;                              /* just below the finger */
    if(y+h>innerHeight-(parseInt(getComputedStyle(document.documentElement).getPropertyValue('--bn'))||0)-pad)
      y=panelAnchor.y-h-18;                              /* flip above if it would overflow */
    var bn=parseInt(getComputedStyle(document.documentElement).getPropertyValue('--bn'))||0;
    var floor=innerHeight-bn-h-pad;      /* never let a panel sit under the bottom bar */
    y=Math.min(Math.max(hh+pad,y), Math.max(hh+pad,floor));
    el.style.left=x+'px'; el.style.top=y+'px';
  });
}
/* phones use a 5-column board with piles in top/bottom strips; wider screens keep the
   traditional side columns, so the row markup differs rather than just its CSS */
function narrowBoard(){return window.matchMedia&&window.matchMedia('(max-width:640px)').matches;}
var fxDraft=false;
function boardNew(){var d=St.decks[simName()];if(!d){board=null;renderSim();return;}
  var deck=[];for(var id in d.main)for(var k=0;k<d.main[id].q;k++)deck.push(+id);
  var ex=[];for(var id in d.extra)for(var k=0;k<d.extra[id].q;k++)ex.push(+id);
  board={deck:shuffle(deck),ex:ex,hand:[],gy:[],ban:[],
    mon:[[],[],[],[],[]],st:[[],[],[],[],[]],emz:[[],[]],fs:[[]],
    /* Opponent side. Mirrored zones plus their own piles; the EMZ above is SHARED, which is
       why it isn't duplicated here. Their deck/extra start empty — this side exists to park
       and attack into their cards, not to goldfish a second deck. */
    omon:[[],[],[],[],[]],ost:[[],[],[],[],[]],ofs:[[]],
    odeck:[],oex:[],ohand:[],ogy:[],oban:[],
    lp:{you:startLP(),opp:startLP()},lpHist:[],log:[],phase:'dp',turn:1};
  sel=null;viewer=null;placeMode='atk';attachMode=false;tokDraft=false;
  fxDraft=false;pmenu=null;renderSim();}
function inst(id){return {id:+id,fd:false,def:false};}
/* A token has no card id — `tok` carries its printed values instead, and every
   reader below checks `it.tok` before reaching for BY[it.id]. */
function tokInst(n,atk,df){return {id:null,tok:{n:n||'Token',atk:atk,df:df},fd:false,def:false};}
function cardOf(it){return it&&it.tok?null:BY[it&&it.id];}
function nameOf(it){return it?(it.tok?it.tok.n:((BY[it.id]||{}).n||'')):'';}
var SLOTS={mon:1,st:1,emz:1,fs:1,omon:1,ost:1,ofs:1};
function isSlot(k){return !!SLOTS[k];}
var OPPZ={omon:1,ost:1,ofs:1,odeck:1,oex:1,ohand:1,ogy:1,oban:1};
function isOpp(k){return !!OPPZ[k];}
/* deck and extra hold bare card ids; every other pile holds instances */
function isIdPile(k){return k==='deck'||k==='ex'||k==='odeck'||k==='oex';}
function zArr(k,s){return isSlot(k)?board[k][s]:board[k];}
function selInst(){if(!sel||!board)return null;
  if(isIdPile(sel.k))return board[sel.k].length?inst(board[sel.k][sel.i]):null;
  var a=zArr(sel.k,sel.s);return a?a[sel.i]:null;}
function selRemove(){if(!sel)return null;var it,id;
  if(isIdPile(sel.k)){id=board[sel.k].splice(sel.i,1)[0];it=inst(id);}
  else{var a=zArr(sel.k,sel.s);it=a.splice(sel.i,1)[0];}
  return it;}
function place(destK,destS){var __n=nameOf(selInst());snap('Move '+__n+' \u2192 '+(PLACE_LABEL[destK]||destK));var it=selRemove();if(!it){sel=null;renderSim();return;}
  /* An Xyz leaving the field sends its materials to the GY — otherwise they'd vanish
     with the host. Moving between field zones keeps them attached. */
  if(!isSlot(destK)&&it.mat&&it.mat.length){
    it.mat.forEach(function(m){m.fd=false;m.def=false;board.gy.push(m);});
    it.mat=[];
  }
  if(isSlot(destK)){
    if(destK==='fs'){it.fd=false;it.def=false;}
    else if(placeMode==='set'){it.fd=true;it.def=(destK==='mon'||destK==='emz');}
    else if(placeMode==='def'){it.fd=false;it.def=true;}
    else{it.fd=false;it.def=false;}
    board[destK][destS].push(it);
    sel={k:destK,s:destS,i:board[destK][destS].length-1};   /* stay on the card */
    renderSim(); return;
  } else if(destK==='deckTop'){board.deck.unshift(it.id);}
  else if(destK==='deckBtm'){board.deck.push(it.id);}
  else if(destK==='off'){/*removed from play*/}
  /* banished face-down: the only destination that keeps a card hidden, so it needs its own
     path — every other pile forces fd=false on the way in */
  else if(destK==='banFD'||destK==='obanFD'){var bk=destK==='banFD'?'ban':'oban';
    it.fd=true;it.def=false;board[bk].push(it);
    sel={k:bk,s:null,i:board[bk].length-1}; renderSim(); return;}
  else if(isIdPile(destK)){board[destK].push(it.id);}        /* deck / extra, either side */
  else if(destK==='hand'||destK==='ohand'){it.fd=false;it.def=false;board[destK].push(it);
    sel={k:destK,s:null,i:board[destK].length-1}; renderSim(); return;}
  else{it.fd=false;board[destK].push(it);
    sel={k:destK,s:null,i:board[destK].length-1}; renderSim(); return;} /* gy, ban, ogy, oban */
  sel=null;renderSim();}
/* fxDraft must reset here: it's global, so leaving it set meant the next card you selected
   (typically straight out of the deck or extra viewer) opened the note field and popped the
   keyboard before you'd asked for anything. */
function bSelect(k,s,i){if(sel&&sel.k===k&&sel.s===s&&sel.i===i)sel=null;else sel={k:k,s:s,i:i};
  viewer=null;fxDraft=false;attachMode=false;pmenu=null;lpOpen=false;phOpen=false;renderSim();}
/* Tapping only ever MOVES a card into an empty zone. Tapping an occupied one selects the
   card sitting there instead — otherwise every tap while something was held flung it across
   the board, which made simply looking around the field impossible. Stacking deliberately
   (Xyz materials, overlays) is still available via Attach or by dragging. */
function bSlotTap(k,s){
  if(dragJustEnded)return;                       /* a drag already handled this */
  var a=board[k][s];
  if(sel&&attachMode){                           /* attach the held card under the monster here */
    if(a&&a.length){var host=a[a.length-1];var it=selRemove();
      if(it){it.fd=false;it.def=false;(host.mat=host.mat||[]).push(it);}
      attachMode=false;renderSim();return;}
    return;                                      /* empty zone: nothing to attach to */
  }
  if(a&&a.length){bSelect(k,s,a.length-1);return;}   /* occupied: take the card, don't displace it */
  if(sel){place(k,s);return;}                        /* empty: place what you're holding */
}

/* ----- Xyz materials ----- */
var attachMode=false;
function bAttach(){attachMode=!attachMode;renderSim();}
function bDetach(){var it=selInst();if(!it||!it.mat||!it.mat.length)return;snap('Detach material');
  var m=it.mat.pop();m.fd=false;m.def=false;board.gy.push(m);renderSim();}
function bViewMat(){var it=selInst();if(!it||!it.mat||!it.mat.length)return;
  viewer='mat';renderSim();}

/* ----- turn phases ----- */
var PHASES=[['dp','DP','Draw Phase'],['sp','SP','Standby Phase'],['m1','M1','Main Phase 1'],
            ['bp','BP','Battle Phase'],['m2','M2','Main Phase 2'],['ep','EP','End Phase']];
function setPhase(p){if(!board)return;snap('Phase \u2192 '+p.toUpperCase());board.phase=p;renderSim();}
function nextPhase(){if(!board)return;
  var i=0;PHASES.forEach(function(p,n){if(p[0]===board.phase)i=n;});
  if(i>=PHASES.length-1)newTurn(); else {board.phase=PHASES[i+1][0];renderSim();}}
function newTurn(){if(!board)return;snap('New turn');board.turn=(board.turn||1)+1;board.phase='dp';renderSim();}
/* compact stand-ins that live in the EMZ row's spare columns */
function phaseMini(){var cur='M1';PHASES.forEach(function(p){if(p[0]===board.phase)cur=p[1];});
  return '<div class=bmini2 onclick="lpOpen=false;pmenu=null;phOpen=!phOpen;renderSim()" title="phase — tap to change">'
    +'<span class=bmlab>PHASE</span><span class=bmval>'+cur+'</span></div>';}
function turnMini(){return '<div class=bmini2 onclick="nextPhase()" title="advance a phase; from EP starts the next turn">'
  +'<span class=bmlab>TURN</span><span class=bmval>'+(board.turn||1)+'</span><span class=bmnext>&rsaquo;</span></div>';}
var phOpen=false;
function phPanel(){if(!phOpen||!board)return '';
  return '<div class="bpmenu phpanel"><span class=btsel>Turn '+(board.turn||1)+'</span><span class=btsep></span>'
    +PHASES.map(function(p){return '<button class="bph'+(board.phase===p[0]?' on':'')+'" title="'+p[2]
      +'" onclick="setPhase(\''+p[0]+'\');phOpen=false;renderSim()">'+p[1]+'</button>';}).join('')
    +'<span class=btsep></span><button onclick="newTurn();phOpen=false;renderSim()">&#8635; New turn</button>'
    +'<span class=btx onclick="phOpen=false;renderSim()" title="close">&times;</span></div>';}
function lpAdj(who,d){if(!board)return;snap('LP '+(who==='you'?'You':'Opp')+' '+(d>0?'+':'')+d);
  var before=board.lp[who];
  board.lp[who]=Math.max(0,before+d);
  board.lpHist.push({w:who,d:board.lp[who]-before});   /* store the APPLIED delta so undo is exact even at 0 */
  renderSim();}
function lpHalf(who){if(!board)return;lpAdj(who,-Math.floor(board.lp[who]/2));}
function lpField(who){var el=document.getElementById('lpIn_'+who);
  var v=parseInt((el&&el.value||'').replace(/[^0-9]/g,''),10);return isNaN(v)?0:v;}
function lpMinus(who){var v=lpField(who);if(v)lpAdj(who,-v);var el=document.getElementById('lpIn_'+who);if(el)el.value='';}
function lpPlus(who){var v=lpField(who);if(v)lpAdj(who,v);var el=document.getElementById('lpIn_'+who);if(el)el.value='';}
function lpUndo(){if(!board||!board.lpHist.length)return;
  var e=board.lpHist.pop();board.lp[e.w]-=e.d;renderSim();}
function lpReset(){if(!board)return;board.lp={you:startLP(),opp:startLP()};board.lpHist=[];renderSim();}

/* ----- declared effects -----
   The board is a manual sim, so it can't know what a card does. Declaring it in your own
   words is what makes a line reviewable afterwards — the note sticks to the card AND lands
   in a running list, which is the seed of the action log in SIM_BOARD_PLAN.md. */
/* Declaring is one tap and records immediately — typing is optional, for when you want to
   clarify what the card is doing. `dec` marks it declared; `fx` holds the optional note. */
function bDeclare(){var it=selInst();if(!it)return;
  snap('Declare '+nameOf(it)+(it.fx?' \u2014 '+it.fx:''));it.dec=true;
  fxDraft=false; renderSim();}
function bNoteOpen(){fxDraft=!fxDraft;renderSim();}
function bNoteSave(){var it=selInst();if(!it){fxDraft=false;renderSim();return;}
  var el=document.getElementById('fxIn'),t=(el&&el.value||'').trim();
  snap('Declare '+nameOf(it)+' \u2014 '+t);it.fx=t; it.dec=true;
  fxDraft=false; renderSim();}
/* Counters and temporary ATK/DEF. Stored on the instance so they travel with the card and
   are captured by undo snapshots for free. oatk/odef are named apart from `def`, which is
   already the defence-position flag. */
function bCtr(d){var it=selInst();if(!it)return;
  snap((d>0?'+1':'-1')+' counter on '+nameOf(it));
  it.ctr=Math.max(0,(it.ctr||0)+d); if(!it.ctr)delete it.ctr; renderSim();}
function bStat(){var it=selInst();if(!it)return;
  var a=document.getElementById('stA'), d2=document.getElementById('stD');
  var av=a&&a.value.trim(), dv=d2&&d2.value.trim();
  snap('Set ATK/DEF on '+nameOf(it));
  if(av==='')delete it.oatk; else it.oatk=parseInt(av,10)||0;
  if(dv==='')delete it.odef; else it.odef=parseInt(dv,10)||0;
  renderSim();}
function bStatClear(){var it=selInst();if(!it)return;
  snap('Reset ATK/DEF on '+nameOf(it)); delete it.oatk; delete it.odef; renderSim();}
function bClearFx(){var it=selInst();if(!it)return;delete it.fx;delete it.dec;renderSim();}
function bDeselect(){sel=null;fxDraft=false;attachMode=false;renderSim();}
/* the full card detail popup, from the board — tokens have no card to show */
function bInfo(){var it=selInst();if(!it||it.tok||!it.id)return;openM(it.id);}
function fxLogClear(){if(!board)return;board.log=[];renderSim();}
/* Collapsed by default — the log is for reviewing a line afterwards, not something you need
   filling the screen while playing. The last entry stays visible in the header either way. */
var logShown=8, logOpen=false;
function fxLogPanel(){
  var n=board.log.length, last=n?board.log[n-1].t:'';
  var h='<div class="bfxlog'+(logOpen?'':' fold')+'">'
    +'<div class=bhlab onclick="logOpen=!logOpen;renderSim()" style="cursor:pointer;display:flex;align-items:center;gap:6px">'
    +'<span class=grpchev>&#9662;</span><span>Action log &middot; '+n+'</span>'
    +(!logOpen&&last?'<span class=blogpeek>'+esc(last)+'</span>':'')
    +'<button class=blogundo onclick="event.stopPropagation();bUndo()"'+(undoStack.length?'':' disabled')+' title="undo the last action">&#8630; Undo</button>'
    +(n&&logOpen?'<span class=qlink style="font-size:10px" onclick="event.stopPropagation();fxLogClear()">clear</span>':'')
    +'</div>';
  if(logOpen)h+=(n?board.log.slice(-logShown).reverse().map(function(e){
      return '<div class=bfxrow>'+esc(e.t||'')+'</div>';}).join('')
      +(n>logShown?'<div class=bfxrow style="border:0"><span class=qlink onclick="logShown+=12;renderSim()">show more</span></div>':'')
     :'<div class=mut style="font-size:11px">Nothing yet.</div>');
  return h+'</div>';}

/* ----- action log & undo -----
   Undo restores a snapshot of the whole board rather than inverting each operation. The
   board is a plain object, so a JSON clone is exact, cheap at this size, and — unlike
   hand-written inverses — cannot drift out of sync as new actions are added. */
var undoStack=[];
function logAct(t){ if(!board)return; board.log.push({t:t});
  if(board.log.length>240)board.log.shift(); }
function snap(desc){ if(!board)return;
  undoStack.push(JSON.stringify(board));          /* taken BEFORE the mutation */
  if(undoStack.length>40)undoStack.shift();
  logAct(desc); }
function bUndo(){ if(!undoStack.length)return;
  board=JSON.parse(undoStack.pop());
  sel=null;pmenu=null;viewer=null;fxDraft=false;attachMode=false;renderSim(); }

/* ----- dice & coin -----
   Both write into the same Declared list as effects, so a line you review afterwards shows
   the rolls in sequence alongside what was activated. */
function bRoll(){if(!board)return;var v=1+Math.floor(Math.random()*6);snap('\u{1F3B2} '+v);
  board.rng={t:'die',v:v}; renderSim();}
function bCoin(){if(!board)return;var v=Math.random()<0.5?'Heads':'Tails';snap('\u{1FA99} '+v);
  board.rng={t:'coin',v:v}; renderSim();}
function rngChip(){if(!board||!board.rng)return '';
  var r=board.rng;
  return '<span class=brng title="latest roll">'+(r.t==='die'?'\u{1F3B2} '+r.v:'\u{1FA99} '+r.v)+'</span>';}

/* ----- tokens ----- */
var tokDraft=false;
function tokOpen(){tokDraft=!tokDraft;renderSim();}
function tokMake(){
  var g=function(id){var e=document.getElementById(id);return e?e.value:'';};
  var n=(g('tkN')||'').trim()||'Token';
  var a=parseInt(g('tkA'),10), d=parseInt(g('tkD'),10);
  var k=null,s=-1,i;
  for(i=0;i<5;i++)if(!board.mon[i].length){k='mon';s=i;break;}
  if(k===null)for(i=0;i<2;i++)if(!board.emz[i].length){k='emz';s=i;break;}
  if(k===null){alert('No free monster zone — move something first.');return;}
  board[k][s].push(tokInst(n,isNaN(a)?null:a,isNaN(d)?null:d));
  tokDraft=false;renderSim();}
function bFlip(){var it=selInst();if(!it)return;snap((it.fd?'Flip up ':'Set down ')+nameOf(it));it.fd=!it.fd;renderSim();}
function bRot(){var it=selInst();if(!it)return;snap((it.def?'To ATK ':'To DEF ')+nameOf(it));it.def=!it.def;renderSim();}
function setPlace(m){placeMode=m;renderSim();}
function bDraw(n){if(!board)return;snap('Draw '+(n||1));for(var i=0;i<(n||1)&&board.deck.length;i++)board.hand.push(inst(board.deck.shift()));sel=null;renderSim();}
function bMillTop(){if(!board||!board.deck.length)return;snap('Mill top');board.gy.push(inst(board.deck.shift()));renderSim();}
function bBanishTop(){if(!board||!board.deck.length)return;snap('Banish top');board.ban.push(inst(board.deck.shift()));renderSim();}
function bShuffle(){if(!board)return;snap('Shuffle deck');board.deck=shuffle(board.deck);sel=null;renderSim();}
function bView(v){viewer=(viewer===v)?null:v;sel=null;pmenu=null;renderSim();}
function bCardHTML(it,seld,mini){var c=cardOf(it),nm=nameOf(it);
  var inner;
  if(it.fd) inner='<div class=bback>&#9672;</div>';
  else if(it.tok) inner='<div class=btok><span class=btokn>'+esc(it.tok.n)+'</span>'
      +((it.tok.atk!=null||it.tok.df!=null)?'<span class=btoka>'+(it.tok.atk!=null?it.tok.atk:'?')+'/'+(it.tok.df!=null?it.tok.df:'?')+'</span>':'')+'</div>';
  else inner='<img draggable="false" src="'+imgSrc(it.id)+'" onerror="this.style.display=\'none\';this.parentNode.classList.add(\'bnoart\')"><span class=bnm>'+esc(nm)+'</span>';
  /* materials sit UNDER this card in it.mat; the badge is the only visible sign, so it
     renders even face-down (an Xyz keeps its materials while face-down) */
  var badge=(it.mat&&it.mat.length)?'<span class=bmat title="Xyz materials">'+it.mat.length+'</span>':'';
  var fx=(it.dec||it.fx)?'<span class=bfx>&#9733;</span>':'';
  var ctr=it.ctr?'<span class=bctr title="counters">'+it.ctr+'</span>':'';
  var st=(it.oatk!=null||it.odef!=null)?'<span class=bstat>'+(it.oatk!=null?it.oatk:'\u2013')+'/'+(it.odef!=null?it.odef:'\u2013')+'</span>':'';
  return '<div class="bcard'+(seld?' bsel':'')+(it.def?' bdef':'')+(mini?' bmini':'')+(it.tok?' btokc':'')+'" title="'+eatt(nm+(it.fd?' (face-down)':'')+(it.def?' (DEF)':'')+(it.mat&&it.mat.length?' · '+it.mat.length+' material'+(it.mat.length===1?'':'s'):'')+(it.fx?' — '+it.fx:''))+'">'+inner+badge+fx+ctr+st+'</div>';}
function slotHTML(k,s,label){var a=board[k][s],has=a&&a.length,seld=sel&&sel.k===k&&sel.s===s;
  var body=has?a.map(function(it,i){return bCardHTML(it,seld&&sel.i===i,false);}).join(''):'<span class=bslab>'+label+'</span>';
  return '<div class="bslot'+(has?'':' bempty')+((sel&&!has)?' bdrop':'')+'" data-z="'+k+'" data-s="'+s+'" onclick="bSlotTap(\''+k+'\','+s+')">'+body+'</div>';}
var FACEUP_PILE={gy:1,ban:1,ogy:1,oban:1};   /* these show their top card; the rest show a back */
function pileHTML(k,label,compact){var a=board[k]||[],n=a.length,top;
  if(FACEUP_PILE[k]&&n)top=bCardHTML(a[n-1],false,true);
  else if(n)top='<div class=bback>&#9672;</div>';
  else top='<span class=bslab>'+label+'</span>';
  /* compact chips show the count alone — the box beneath already carries the name, and
     "EXTRA · 0" overlaps its neighbours in a 46px column */
  return '<div class="bpile'+(n?'':' bempty')+(compact?' bpc':'')+'" data-pile="'+k+'" onclick="bPileTap(\''+k+'\')"><div class=bpcount>'+(compact?n:label+' &middot; '+n)+'</div><div class=bptop>'+top+'</div></div>';}
/* Tapping a pile opens a small action menu rather than dumping you straight into the
   viewer — drawing, milling and banishing are what you actually want most of the time,
   and they used to live in a control bar far above the field. */
var pmenu=null;
/* Destination for each pile when a card is already in hand — deck means the top. */
var PLACE_LABEL={hand:'hand',gy:'GY',ban:'banished',banFD:'banished face-down',ohand:'opp hand',ogy:'opp GY',oban:'opp banished',obanFD:'opp banished FD',ex:'extra',deckTop:'deck top',deckBtm:'deck bottom',off:'out of play',mon:'monster zone',st:'S/T zone',emz:'EMZ',fs:'field',omon:'opp monster',ost:'opp S/T',ofs:'opp field'};
var PILE_DEST={deck:'deckTop',ex:'ex',gy:'gy',ban:'ban',hand:'hand',
  odeck:'odeck',oex:'oex',ogy:'ogy',oban:'oban',ohand:'ohand'};
/* A pile always opens its menu — never grabs the top card, never swallows what you're
   holding. If a card IS held the menu offers to send it there, so both intents are explicit. */
function bPileTap(k){ if(dragJustEnded)return;
  pmenu=(pmenu===k)?null:k; viewer=null; lpOpen=false; phOpen=false; renderSim(); }
function pmClose(){ pmenu=null; renderSim(); }
function pmAct(a){
  var k=pmenu; if(!k){return;}
  var isMine=!isOpp(k);
  if(a==='view'){ pmenu=null; bView(k); return; }
  if(a==='send'){ var dest=PILE_DEST[k]||k; pmenu=null; place(dest); return; }
  if(a==='sendfd'){ pmenu=null; place(k==='oban'?'obanFD':'banFD'); return; }
  if(a==='banishfd'){ if(board.deck.length)board.ban.push((function(){var it=inst(board.deck.shift());it.fd=true;return it;})()); renderSim(); return; }
  if(k==='deck'){
    if(a==='draw')bDraw(1); else if(a==='draw5')bDraw(5); else if(a==='draw6')bDraw(6);
    else if(a==='mill')bMillTop(); else if(a==='banish')bBanishTop();
    else if(a==='shuffle')bShuffle();
  } else if(k==='odeck'){
    var d=board.odeck;
    if(a==='draw'&&d.length)board.ohand.push(inst(d.shift()));
    else if(a==='mill'&&d.length)board.ogy.push(inst(d.shift()));
    else if(a==='banish'&&d.length)board.oban.push(inst(d.shift()));
    else if(a==='shuffle')board.odeck=shuffle(d);
  }
  renderSim();          /* menu stays open — closing it after every draw was jarring */
}
function pmenuHTML(){ if(!pmenu||!board)return '';
  var k=pmenu, n=(board[k]||[]).length;
  var held=selInst();
  var b='<button class=bprim onclick="pmAct(\'view\')">&#128065; View'+(n?' ('+n+')':'')+'</button>';
  if(held){ b+='<button class=bprim onclick="pmAct(\'send\')">&#8595; Send '+esc(nameOf(held))+' here</button>';
    if(k==='ban'||k==='oban')b+='<button onclick="pmAct(\'sendfd\')">&#8595; Send face-down</button>'; }
  if(k==='deck'||k==='odeck'){
    b+='<button class=bprim onclick="pmAct(\'draw\')">Draw</button>';
    if(k==='deck')b+='<button onclick="pmAct(\'draw5\')">Open 5</button><button onclick="pmAct(\'draw6\')">Open 6</button>';
    b+='<span class=btsep></span><button onclick="pmAct(\'mill\')">Mill top</button>'
      +'<button onclick="pmAct(\'banish\')">Banish top</button>'
      +'<button onclick="pmAct(\'banishfd\')" title="banish the top card face-down">Banish top FD</button>'
      +'<button onclick="pmAct(\'shuffle\')">&#128256; Shuffle</button>';
  }
  return '<div class=bpmenu><span class=btsel>'+esc(PILE_LABEL[k]||k)+' &middot; '+n+'</span>'
    +'<span class=btsep></span>'+b
    +'<span class=btx onclick="pmClose()" title="close">&times;</span></div>';}
function boardToolbar(){
  /* Suppressed while another panel is up: only one menu is ever on screen. `sel` is kept,
     not cleared, so the pile menu can still offer to send the held card. */
  if(pmenu||lpOpen||phOpen)return '';
  var it=selInst();if(!it)return '';var onField=isSlot(sel.k);
  var h='<div class=btoolbar><span class=btsel>'+esc(nameOf(it))+(it.fd?' &middot; face-down':'')+(it.def?' &middot; DEF':'')+'</span><span class=btsep></span>'
    +'<span class=mut style="font-size:11px">place as</span>'
    +'<button class="'+(placeMode==='atk'?'bon':'')+'" onclick="setPlace(\'atk\')">ATK</button>'
    +'<button class="'+(placeMode==='def'?'bon':'')+'" onclick="setPlace(\'def\')">DEF</button>'
    +'<button class="'+(placeMode==='set'?'bon':'')+'" onclick="setPlace(\'set\')">Set</button>'
    +'<span class=mut style="font-size:11px">&rarr; then tap a zone</span><span class=btsep></span>';
  /* On the field these two are the actions reached for constantly, so they lead and say
     what the card will BECOME rather than naming the operation. */
  if(onField)h+='<button class=bprim onclick="bFlip()">'+(it.fd?'&#128065; Flip face-up':'&#9632; Set face-down')+'</button>'
    +'<button class=bprim onclick="bRot()">'+(it.def?'&#8593; To ATK':'&#8635; To DEF')+'</button><span class=btsep></span>';
  /* Xyz materials: "Attach" arms the next zone tap; detach peels one off to the GY */
  h+='<button class="'+(attachMode?'bon':'')+'" onclick="bAttach()" title="attach this card under a monster as an Xyz material">'+(attachMode?'Attach &rarr; tap a monster':'Attach')+'</button>';
  if(it.mat&&it.mat.length)h+='<button onclick="bViewMat()">Materials ('+it.mat.length+')</button><button onclick="bDetach()">Detach &rarr; GY</button>';
  h+='<span class=btsep></span>';
  if(onField){
    h+='<span class=btsep></span><span class=mut style="font-size:11px">ctr</span>'
      +'<button onclick="bCtr(-1)">&minus;</button><span class=btsel style="width:auto;min-width:14px;text-align:center">'+(it.ctr||0)+'</span><button onclick="bCtr(1)">+</button>'
      +'<input type=text id=stA class=gnum inputmode=numeric placeholder="ATK" value="'+(it.oatk!=null?it.oatk:'')+'" style="width:58px">'
      +'<input type=text id=stD class=gnum inputmode=numeric placeholder="DEF" value="'+(it.odef!=null?it.odef:'')+'" style="width:58px">'
      +'<button onclick="bStat()">Set</button>'
      +((it.oatk!=null||it.odef!=null)?'<button onclick="bStatClear()">reset</button>':'');
  }
  if(!it.tok)h+='<button onclick="bInfo()" title="card text, printings and prices">&#8505; Info</button>';
  h+='<button onclick="bDeclare()" title="record that this card activated">'+(it.dec?'Declared &#9733;':'Declare')+'</button>';
  if(fxDraft)h+='<input type=text id=fxIn placeholder="optional: what is it doing?" value="'+eatt(it.fx||'')+'" style="min-width:170px" onkeydown="if(event.key===\'Enter\')bNoteSave()"><button onclick="bNoteSave()">Save note</button>';
  else h+='<button onclick="bNoteOpen()" title="optional note to clarify">&#9998; note</button>';
  if((it.fx||it.dec)&&!fxDraft)h+='<button onclick="bClearFx()" title="clear the declaration">clear</button>';
  h+='<span class=btsep></span>';
  h+='<button onclick="place(\'hand\')">Hand</button><button onclick="place(\'gy\')">GY</button>'
    +'<button onclick="place(\'ban\')">Banish</button>'
    +'<button onclick="place(\'banFD\')" title="banish face-down">Banish FD</button>'
    +'<button onclick="place(\'deckTop\')">Deck top</button><button onclick="place(\'deckBtm\')">Deck btm</button>'
    +'<button onclick="place(\'ex\')">Extra</button>'
    +'<span class=btsep></span><button onclick="place(\'off\')" title="remove from play">&times; off</button>'
    +'<span class=btx onclick="bDeselect()" title="close">&times;</span></div>';
  return h;}
/* Tapping the hand area returns the held card, the same way tapping a zone or pile does —
   it was a drop target for drags but had no click path. */
function bHandZoneTap(){ if(dragJustEnded)return; if(sel)place('hand'); }
function oppHandHTML(){
  var h='<div class="bhandwrap bophand" data-pile="ohand" onclick="bOppHandTap()">'
    +'<div class=bhlab>Opponent hand &middot; '+board.ohand.length+'</div><div class=bhcards>';
  h+=board.ohand.map(function(it,i){return '<div data-z="ohand" data-i="'+i+'" onclick="event.stopPropagation();bOppHandCardTap('+i+')">'
    +bCardHTML(it,sel&&sel.k==='ohand'&&sel.i===i,false)+'</div>';}).join('');
  return h+'</div></div>';}
function bOppHandTap(){ if(dragJustEnded)return; if(sel)place('ohand'); }
function bOppHandCardTap(i){ if(dragJustEnded)return; bSelect('ohand',null,i); }
function handHTML(){var h='<div class=bhandwrap data-pile="hand" onclick="bHandZoneTap()"><div class=bhlab>Hand &middot; '+board.hand.length+'<span class=bhhint>'+(sel?' &mdash; tap to return the card':'')+'</span></div><div class=bhcards>';
  h+=board.hand.map(function(it,i){return '<div data-z="hand" data-i="'+i+'" onclick="event.stopPropagation();bHandTap('+i+')">'+bCardHTML(it,sel&&sel.k==='hand'&&sel.i===i,false)+'</div>';}).join('');
  return h+'</div></div>';}
function bHandTap(i){ if(dragJustEnded)return; bSelect('hand',null,i); }
function bMatDetach(i){var host=selInst();if(!host||!host.mat||!host.mat[i])return;
  var m=host.mat.splice(i,1)[0];m.fd=false;m.def=false;board.gy.push(m);
  if(!host.mat.length)viewer=null;renderSim();}
var PILE_LABEL={deck:'Deck',ex:'Extra Deck',gy:'Graveyard',ban:'Banished',hand:'Hand',
  odeck:'Opponent deck',oex:'Opponent extra',ogy:'Opponent graveyard',oban:'Opponent banished',ohand:'Opponent hand'};
function viewerHTML(){if(!viewer)return '';var k=viewer,title,arr,act;
  if(isIdPile(k)){title=PILE_LABEL[k]+' ('+board[k].length+')';arr=board[k].map(function(id,i){return {it:{id:id},i:i};});}
  else if(k==='mat'){var host=selInst();
    if(!host||!host.mat||!host.mat.length){viewer=null;return '';}
    title='Xyz materials ('+host.mat.length+') &mdash; tap one to detach to the GY';
    arr=host.mat.map(function(it,i){return {it:it,i:i};});
    act=function(i){return 'bMatDetach('+i+')';};}
  else{title=(PILE_LABEL[k]||k)+' ('+board[k].length+')';arr=board[k].map(function(it,i){return {it:it,i:i};});}
  if(!act)act=function(i){return 'bSelect(\''+k+'\',null,'+i+')';};
  var cards=arr.map(function(o){var it=o.it;
    var body=it.tok
      ? '<div class=btok><span class=btokn>'+esc(it.tok.n)+'</span></div>'
      : '<img draggable="false" src="'+imgSrc(it.id)+'" onerror="this.style.display=\'none\';this.parentNode.classList.add(\'bnoart\')"><span class=bnm>'+esc(nameOf(it))+'</span>';
    /* art still shows — it's your own card and you need to find it — but face-down has to be
       unmistakable, since it changes what you may legally do with it */
    var fd=it.fd?'<span class=bvfd>face-down</span>':'';
    return '<div class="bvcard'+(it.fd?' bvfdc':'')+'" onclick="'+act(o.i)+'">'+body+fd+'</div>';}).join('');
  return '<div class=bviewer onclick="bView(\''+k+'\')"><div class=bvbox onclick="event.stopPropagation()">'
    +'<div class=bvhead><b>'+title+'</b>'+(k==='deck'?' <span class=mut style="font-size:11px">order hidden &mdash; pick any card to act on it</span>':'')+'<button onclick="bView(\''+k+'\')" style="margin-left:auto">Close</button></div>'
    +'<div class=bvcards>'+(cards||'<span class=mut>Empty.</span>')+'</div></div></div>';}
function lpSide(who,label){var v=board.lp[who];
  return '<div class="lpside'+(v<=0?' lpout':'')+'">'
    +'<div class=lplab>'+label+'</div>'
    +'<div class=lpval>'+v.toLocaleString()+'</div>'
    +'<div class=lpq><button onclick="lpAdj(\''+who+'\',-100)">&minus;100</button>'
    +'<button onclick="lpAdj(\''+who+'\',-500)">&minus;500</button>'
    +'<button onclick="lpAdj(\''+who+'\',-1000)">&minus;1000</button>'
    +'<button onclick="lpHalf(\''+who+'\')" title="halve">&frac12;</button></div>'
    +'<div class=lpq><input type=text id="lpIn_'+who+'" class=lpin inputmode=numeric placeholder="amount">'
    +'<button onclick="lpMinus(\''+who+'\')">&minus;</button><button onclick="lpPlus(\''+who+'\')">+</button></div>'
    +'</div>';}
/* On a phone the two LP cards ate the top of the screen. The EMZ row's middle column is
   empty by definition, so the running totals live there as a chip that opens the full
   calculator on demand. The wide bar is kept for desktop, where the room exists. */
var lpOpen=false;
function lpToggle(){lpOpen=!lpOpen; if(lpOpen){pmenu=null;phOpen=false;} renderSim();}
function lpChip(){return '<div class=lpchip onclick="lpToggle()" title="life points — tap for the calculator">'
  +'<span class=lpcv>'+board.lp.you.toLocaleString()+'</span>'
  +'<span class=lpcs>LP</span>'
  +'<span class="lpcv lpco">'+board.lp.opp.toLocaleString()+'</span></div>';}
function lpPanel(){if(!lpOpen||!board)return '';
  return '<div class="bpmenu lppanel">'+lpSide('you','You')+lpSide('opp','Opponent')
    +'<div class=lpmeta><button onclick="lpUndo()"'+(board.lpHist.length?'':' disabled')+'>Undo</button>'
    +'<button onclick="lpReset()">Reset</button><button onclick="lpToggle()">Close</button></div></div>';}
/* Wide screens have a lot of dead space either side of the field, so the two things you
   otherwise open one-at-a-time live there permanently: what the selected card actually does,
   and the contents of whichever pile you're working with. Hidden below 1200px, where the
   modal/overlay versions remain the only sensible option. */
function sideInfoHTML(){ var b=sideInfoBody(hoverIt||selInst(),!!hoverIt);
  return '<div class="bsidepanel bsideleft'+(b?'':' bsempty')+'">'+b+'</div>'; }
function sideInfoBody(it,isHover){
  if(!it)return '';
  var c=cardOf(it);
  var h='<div class=bsphead>'+(isHover?'Hovering':'Selected')+'</div>';
  if(it.tok){h+='<div class=bspname>'+esc(it.tok.n)+'</div><div class=bspmeta>Token'
    +(it.tok.atk!=null?' &middot; ATK '+it.tok.atk:'')+(it.tok.df!=null?' / DEF '+it.tok.df:'')+'</div>';}
  else if(c){
    h+='<img class=bspimg draggable="false" src="'+imgSrc(c.i)+'" onerror="this.style.display=\'none\'">'
      +'<div class=bspname>'+esc(c.n)+'</div>'
      +'<div class=bspmeta>'+esc(c.cl)+(c.rc?' &middot; '+esc(c.rc):'')+(c.at?' &middot; '+esc(c.at):'')
      +(c.lv!=null?' &middot; Lv'+c.lv:'')+(c.atk!=null?' &middot; '+c.atk+'/'+(c.df==null?'?':c.df):'')+'</div>'
      +(c.bn&&c.bn!=='Unlimited'?'<div class=bspban>'+esc(c.bn)+'</div>':'')
      +'<div class=bsptext>'+esc(c.tx||'')+'</div>'
      +'<div class=bspmeta>Market '+f(c.m)+(c.hr?' &middot; '+esc(c.hr):'')+'</div>';
  }
  if(it.fx)h+='<div class=bspfx>&#9733; '+esc(it.fx)+'</div>';
  if(it.mat&&it.mat.length)h+='<div class=bspmeta>'+it.mat.length+' Xyz material'+(it.mat.length===1?'':'s')+'</div>';
  return h;}

/* Hovering a card fills the left panel without a full board redraw — it falls back to the
   selected card when the pointer leaves, so the panel is never blank while something is held. */
var hoverIt=null;
function paintSideInfo(){var el=document.querySelector('.bsideleft');
  if(!el)return;
  var b=sideInfoBody(hoverIt||selInst(),!!hoverIt);
  el.innerHTML=b; el.classList.toggle('bsempty',!b);}
function instAt(cardEl){
  var host=cardEl.closest('[data-z],[data-pile]'); if(!host||!board)return null;
  var z=host.getAttribute('data-z');
  if(z==='hand'||z==='ohand')return board[z][+host.getAttribute('data-i')];
  if(z)return (board[z][+host.getAttribute('data-s')]||[]).slice(-1)[0];
  var pk=host.getAttribute('data-pile'); if(!pk)return null;
  var a=board[pk]||[]; if(!a.length)return null;
  return isIdPile(pk)?{id:a[a.length-1]}:a[a.length-1];
}
addEventListener('pointerover',function(e){
  if(typeof view==='undefined'||view!=='sim'||!board)return;
  if(!e.target||!e.target.closest)return;
  var cardEl=e.target.closest('.bcard,.bvcard');
  if(!cardEl){ if(hoverIt){hoverIt=null;paintSideInfo();} return; }
  var it=cardEl.classList.contains('bvcard')?null:instAt(cardEl);
  if(it!==hoverIt){hoverIt=it;paintSideInfo();}
});
var SIDE_CAP=60;   /* a full deck is thousands of cards; the panel is a peek, not the viewer */
function sidePileHTML(){
  var k=pmenu||viewer;
  /* deliberately excludes deck/odeck: the main deck is hidden information, and showing it
     permanently would spoil every draw. It's still inspectable via the pile menu's View. */
  var OPEN_PILES={gy:1,ban:1,ogy:1,oban:1,ex:1,oex:1};
  if(!k||!OPEN_PILES[k])return '<div class="bsidepanel bsideright bsempty"></div>';
  var a=board[k]||[];
  var h='<div class="bsidepanel bsideright"><div class=bsphead>'+esc(PILE_LABEL[k]||k)+' &middot; '+a.length+'</div>';
  if(!a.length)h+='<div class=mut style="font-size:11px">Empty.</div>';
  else h+=(a.length>SIDE_CAP?'<div class=bspmeta style="margin:0 0 6px">newest '+SIDE_CAP+' of '+a.length+' &mdash; open View for all</div>':'')
    +'<div class=bspgrid>'+a.slice().reverse().slice(0,SIDE_CAP).map(function(it,ri){
    var i=a.length-1-ri, id=isIdPile(k)?it:it.id, fd=!isIdPile(k)&&it.fd;
    return '<div class="bvcard'+(fd?' bvfdc':'')+'" title="'+eatt(isIdPile(k)?((BY[id]||{}).n||''):nameOf(it))+'" onclick="bSelect(\''+k+'\',null,'+i+')">'
      +'<img draggable="false" src="'+imgSrc(id)+'" onerror="this.style.display=\'none\';this.parentNode.classList.add(\'bnoart\')">'
      +'<span class=bnm>'+esc(isIdPile(k)?((BY[id]||{}).n||''):nameOf(it))+'</span>'
      +(fd?'<span class=bvfd>face-down</span>':'')+'</div>';}).join('')+'</div>';
  return h+'</div>';}
function renderBoard(toggle){var h=toggle,decks=Object.keys(St.decks);
  h+='<div class=bctrl><label class=mut>Deck <select onchange="simDeck=this.value;boardNew()">'+decks.map(function(nm){return '<option'+(nm===simName()?' selected':'')+'>'+esc(nm)+'</option>';}).join('')+'</select></label>'
    +'<button onclick="boardNew()">&#8635; New game</button>';
  /* Draw / mill / banish / shuffle moved onto the deck's own menu — they were stranded up
     here, far above the field you're actually looking at. */
  if(board)h+='<button class="'+(tokDraft?'bon':'')+'" onclick="tokOpen()">&#10011; Token</button>'
    +'<button onclick="bRoll()" title="roll a six-sided die">&#127922; Die</button>'
    +'<button onclick="bCoin()" title="flip a coin">&#129689; Coin</button>'+rngChip();
  h+='</div>';
  if(board&&tokDraft)h+='<div class=btokform>'
    +'<input type=text id=tkN placeholder="token name" style="min-width:150px">'
    +'<input type=text id=tkA class=gnum inputmode=numeric placeholder="ATK" style="width:74px">'
    +'<input type=text id=tkD class=gnum inputmode=numeric placeholder="DEF" style="width:74px">'
    +'<button onclick="tokMake()">Create</button><button onclick="tokOpen()">Cancel</button>'
    +'<span class=mut style="font-size:11px">goes to the first free monster zone &mdash; drag it anywhere after</span></div>';
  if(board)h+=lpPanel()+phPanel()+pmenuHTML();
  if(!board){h+='<div class=ins style="margin-top:12px">Pick a deck and press <b>New game</b>. Then <b>tap the Deck</b> to draw or search it, <b>tap a hand card</b> then a field zone to summon or set, and <b>tap any pile</b> (GY, Banished, Extra) to open it and act on the cards inside &mdash; the way DuelingBook works.</div>';document.getElementById('simBody').innerHTML=h;return;}
  h+=boardToolbar();
  /* always present, just emptied — a hint that appears and disappears changes the document
     height and shifts everything below it */
  h+='<div class=bhint>'+(sel?'&nbsp;':'Drag a card to a zone, or tap it then tap the zone.')+'</div>';
  h+='<div class=bfield>';
  /* Opponent side is a true 180-degree mirror of yours: hand at the far edge, then S/T with
     deck and extra flanking it, then monsters with graveyard and field spell flanking, and
     their banished sits opposite yours across the shared EMZ row. */
  h+=oppHandHTML();
  h+='<div class="bmainrow bopp"><div class=bside>'+pileHTML('odeck','Deck')+'</div>'
    +'<div class=bzones>'+[0,1,2,3,4].map(function(s){return slotHTML('ost',s,'S'+(5-s));}).join('')+'</div>'
    +'<div class=bside>'+pileHTML('oex','Extra')+'</div></div>';
  h+='<div class="bmainrow bopp"><div class=bside>'+pileHTML('ogy','GY')+'</div>'
    +'<div class=bzones>'+[0,1,2,3,4].map(function(s){return slotHTML('omon',s,'M'+(5-s));}).join('')+'</div>'
    +'<div class=bside>'+slotHTML('ofs',0,'Field')+'</div></div>';
  /* The EMZ row's three spare columns carry the phase control, life points and the turn —
     they were empty, and each of those used to cost a full row above the field. */
  h+='<div class=bemzrow><div class=bemzoban>'+pileHTML('oban','Ban')+'</div>'
    +'<div class="bemzside bemzphase">'+phaseMini()+'</div>'
    +slotHTML('emz',0,'EMZ')+lpChip()+slotHTML('emz',1,'EMZ')
    +'<div class="bemzside bemzturn">'+turnMini()+'</div>'
    +'<div class=bemzban>'+pileHTML('ban','Ban')+'</div></div>';
  h+='<div class=bmainrow><div class=bside>'+slotHTML('fs',0,'Field')+'</div><div class=bzones>'+[0,1,2,3,4].map(function(s){return slotHTML('mon',s,'M'+(s+1));}).join('')+'</div><div class=bside>'+pileHTML('gy','GY')+'</div></div>';
  h+='<div class=bmainrow><div class=bside>'+pileHTML('ex','Extra')+'</div><div class=bzones>'+[0,1,2,3,4].map(function(s){return slotHTML('st',s,'S'+(s+1));}).join('')+'</div><div class=bside>'+pileHTML('deck','Deck')+'</div></div>';
  h+='</div>';
  h+=handHTML();
  h+=sideInfoHTML()+sidePileHTML();
  h+=fxLogPanel();
  h+=viewerHTML();
  /* Rebuilding the board replaces the whole subtree, and any height change — the hint line
     appearing, the hand caption growing — moved the page under you when a panel opened.
     Hold the scroll position across the swap. */
  var y=window.scrollY;
  document.getElementById('simBody').innerHTML=h;
  if(window.scrollY!==y)window.scrollTo(0,y);
  placePanels();
  if(fxDraft){var fi=document.getElementById('fxIn');if(fi){fi.focus({preventScroll:true});fi.select();}}}

/* ===== tap-and-drag =======================================================
   Pointer events rather than HTML5 drag-and-drop, which doesn't work on touch.
   Tap-to-move still works: a press only becomes a drag past an 8px threshold,
   and below that the existing onclick handlers run untouched. renderSim()
   rebuilds the board via innerHTML, so nothing is re-rendered mid-drag —
   listeners are delegated from document and the ghost lives on <body>.
   ========================================================================= */
(function(){
var dragS=null, ghost=null;
function srcOf(cardEl){
  var host=cardEl.closest('[data-z]'); if(!host)return null;
  var k=host.getAttribute('data-z');
  if(k==='hand')return {k:'hand',s:null,i:+host.getAttribute('data-i')};
  var kids=host.querySelectorAll(':scope > .bcard');
  var i=Array.prototype.indexOf.call(kids,cardEl);
  return {k:k,s:+host.getAttribute('data-s'),i:i<0?kids.length-1:i};
}
function ghostStart(el,e){ ghost=el.cloneNode(true); ghost.className='bcard bghost';
  document.body.appendChild(ghost); ghostMove(e); }
function ghostMove(e){ if(ghost){ghost.style.left=e.clientX+'px';ghost.style.top=e.clientY+'px';} }
function clearHot(){ Array.prototype.forEach.call(document.querySelectorAll('.bhot'),
  function(el){el.classList.remove('bhot');}); }
function ghostEnd(){ if(ghost&&ghost.parentNode)ghost.parentNode.removeChild(ghost); ghost=null;
  clearHot(); Array.prototype.forEach.call(document.querySelectorAll('.bdim'),
    function(el){el.classList.remove('bdim');}); }
function dropAt(x,y){
  if(ghost)ghost.style.display='none';              /* the ghost is under the cursor */
  var el=document.elementFromPoint(x,y);
  if(ghost)ghost.style.display='';
  if(!el||!el.closest)return null;
  var p=el.closest('[data-pile]'); if(p)return {pile:p.getAttribute('data-pile')};
  var z=el.closest('[data-z]'); if(!z)return null;
  var k=z.getAttribute('data-z');
  return k==='hand'?{pile:'hand'}:{k:k,s:+z.getAttribute('data-s')};
}
/* Drag arms on movement, with no hold delay — the wait read as lag. Cards carry
   touch-action:none, so a swipe starting on one was never going to scroll the page
   anyway, which is what the hold was guarding against. */
var SLOP=7;
function cancelDrag(){ if(dragS&&dragS.el)dragS.el.classList.remove('bheld'); dragS=null; }
addEventListener('pointerdown',function(e){
  if(typeof view==='undefined'||view!=='sim'||!board||viewer)return;
  if(!e.target||!e.target.closest)return;
  var cardEl=e.target.closest('.bcard');
  if(!cardEl||cardEl.classList.contains('bghost'))return;
  var src=srcOf(cardEl); if(!src)return;            /* pile tops aren't draggable */
  dragS={src:src,x0:e.clientX,y0:e.clientY,el:cardEl,on:false};
},{passive:true});
addEventListener('pointermove',function(e){
  if(!dragS)return;
  if(!dragS.on){
    if(Math.abs(e.clientX-dragS.x0)+Math.abs(e.clientY-dragS.y0)<SLOP)return;
    dragS.on=true; ghostStart(dragS.el,e); dragS.el.classList.add('bdim');
  }
  ghostMove(e);
  clearHot();
  var t=dropAt(e.clientX,e.clientY); if(!t)return;
  var q=t.pile?'[data-pile="'+t.pile+'"]':'[data-z="'+t.k+'"][data-s="'+t.s+'"]';
  var el=document.querySelector(q); if(el)el.classList.add('bhot');
});
addEventListener('pointerup',function(e){
  if(!dragS)return; var d=dragS;
  if(d.el)d.el.classList.remove('bheld');
  dragS=null;
  if(!d.on)return;                                  /* never moved: it was a tap */
  ghostEnd();
  /* the click event fires right after this; the tap handlers check this flag */
  dragJustEnded=true; setTimeout(function(){dragJustEnded=false;},0);
  var t=dropAt(e.clientX,e.clientY);
  if(!t){renderSim();return;}
  sel=d.src;
  var toPile={hand:'hand',gy:'gy',ban:'ban',ex:'ex',deck:'deckTop'};
  if(t.pile)place(toPile[t.pile]||'hand');
  else place(t.k,t.s);
});
addEventListener('pointercancel',function(){ if(dragS){ghostEnd();cancelDrag();} });
/* belt and braces for the callout: some iOS builds still raise it despite the CSS */
addEventListener('contextmenu',function(e){
  if(e.target&&e.target.closest&&e.target.closest('.bfield,.bhandwrap,.bviewer'))e.preventDefault();
});
/* The card menu now persists after an action so you can keep working on the same card, which
   means it needs a way out: anywhere off the board, the menus, or the hand dismisses it. */
addEventListener('click',function(e){
  if(typeof view==='undefined'||view!=='sim'||!board||dragJustEnded)return;
  if(!e.target||!e.target.closest)return;
  if(e.target.closest('.bfield,.bhandwrap,.btoolbar,.bpmenu,.bviewer,#ov,.bctrl,.btokform'))return;
  if(sel||pmenu||lpOpen||phOpen){
    sel=null;pmenu=null;lpOpen=false;phOpen=false;fxDraft=false;attachMode=false;renderSim();
  }
});
})();

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
  else lb+='<div class=tscroll><table><tr><th>Date</th><th>Event</th><th>My deck</th><th>Opponent</th><th>Result</th><th>P/D</th><th>Games</th><th>Note</th><th></th></tr>'+fm.map(function(m){var rc=m.res==='W'?'var(--pos)':m.res==='L'?RED:'var(--mut)',rl=m.res==='W'?'Win':m.res==='L'?'Loss':'Tie';
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
    +'<div class=tscroll><table><tr><th>Set</th><th>Code</th><th class=r>Cards</th><th class=r>Total value</th><th>Newest card</th></tr>'
    +shown.map(function(o){return '<tr class=setrow onclick="openSet('+o.i+')"><td class=nm>'+esc(o.s.n)+'</td><td class=mut>'+esc(o.s.c||'')+'</td><td class="r">'+o.a.cards+'</td><td class="r">'+f(o.a.tot||null)+'</td><td class=mut>'+(o.a.date?fdate(o.a.date):'—')+'</td></tr>';}).join('')+'</table></div>';}
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
  h+='<h2 class=sec>Cards ('+cs.length+')</h2><div class=tscroll><table><tr><th>Card</th><th>Rarities in set</th><th class=r>Market low</th></tr>'
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
/* Profile & settings. Everything about *you* rather than about cards: who you're signed in
   as, where your data lives and how to get a copy of it, and the defaults the board uses.
   This is also the shell the marketplace and public profiles will hang off later. */
function setStartLP(v){var n=parseInt(String(v).replace(/[^0-9]/g,''),10);
  if(isNaN(n)||n<=0)n=8000; St.settings=St.settings||{}; St.settings.startLP=n; sv(); renderYou();}
function startLP(){return (St.settings&&St.settings.startLP)||8000;}
function youSignOut(){if(window.syncSignOut)syncSignOut();setTimeout(renderYou,400);}
function renderYou(){
  var sy=(window.syncInfo?syncInfo():{state:'off',email:'',last:0});
  var stateText={idle:'Synced',syncing:'Syncing…',pending:'Saving…',offline:'Offline — will sync when back',
    error:'Sync error',conflict:'Needs your choice',signedout:'Not signed in',
    off:'Off in this build',unconfigured:'Not set up'}[sy.state]||'Unknown';
  var h='<h2 class=sec>Account</h2>'
    +'<div class=deckstats style="display:flex;gap:16px;flex-wrap:wrap;align-items:center">'
      +'<div><div class=mut style="font-size:11px">SYNC</div><div style="font-size:17px;font-weight:700">'+esc(stateText)+'</div></div>'
      +(sy.email?'<div><div class=mut style="font-size:11px">SIGNED IN AS</div><div style="font-size:14px">'+esc(sy.email)+'</div></div>':'')
      +(sy.last?'<div><div class=mut style="font-size:11px">LAST SYNCED</div><div style="font-size:14px">'+Math.max(0,Math.round((Date.now()-sy.last)/60000))+' min ago</div></div>':'')
      +'</div>'
    +'<div class=bar>'
      +(sy.email?'<button onclick="if(window.syncNow)syncNow()">Sync now</button><button onclick="youSignOut()">Sign out</button>'
                :'<button onclick="if(window.syncOpen)syncOpen()">Sign in to sync</button>')
    +'</div>'
    +'<div class=mut style="font-size:11.5px;line-height:1.6;max-width:620px">Signing in keeps your collection, decks, budget and match log on every device. '
      +'Your data lives in your browser and, when signed in, in your own row on the server &mdash; nobody else can read it.</div>'

    +'<h2 class=sec>Your data</h2>'
    +'<div class=bar><button onclick="exJson()">Backup all (.json)</button>'
      +'<button onclick="imp.click()">Import backup</button></div>'
    +'<div class=mut style="font-size:11.5px;line-height:1.6;max-width:620px">A backup is the only copy that does not depend on this browser or the sync server. '
      +'Worth taking one occasionally.</div>'

    +'<h2 class=sec>Board defaults</h2>'
    +'<div class=bar><label class=mut style="font-size:12px">Starting life points '
      +'<input type=text class=num inputmode=numeric value="'+startLP()+'" onchange="setStartLP(this.value)" style="width:88px;margin-left:6px"></label>'
      +'<button onclick="setStartLP(8000)">Reset to 8000</button></div>'

    +'<h2 class=sec>About</h2>'
    +'<div class=ovw>'
      +'<div class=ost><div class=v>'+CARDS.length.toLocaleString()+'</div><div class=l>cards</div></div>'
      +'<div class=ost><div class=v>'+(SETS?SETS.length.toLocaleString():0)+'</div><div class=l>sets</div></div>'
      +'<div class=ost><div class=v style="font-size:15px">__DATE__</div><div class=l>price snapshot</div></div>'
      +'<div class=ost><div class=v style="font-size:15px">__BUILD__</div><div class=l>build</div></div>'
    +'</div>'
    +'<div class=mut style="font-size:11.5px;line-height:1.6;max-width:620px">Prices come from the free YGOPRODeck feed and are estimates &mdash; '
      +'many printings are unpriced. Set your own value in the <b>Unit</b> column of your Collection where it matters.</div>';
  document.getElementById('youBody').innerHTML=h;}
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
  else imp+='<div class=tscroll style="margin-top:10px"><table><tr><th>Deck</th><th>Tier</th><th class=r>Cards</th><th class=r>Value</th><th class=r>Cost to you</th><th></th></tr>'+M.map(function(d){
    var val=0,toyou=0;for(var id in d.cnt){var c=BY[id];if(!c||c.m==null)continue;val+=c.m*d.cnt[id];toyou+=c.m*Math.max(0,d.cnt[id]-owned(id));}
    return '<tr><td class=nm onclick="metaRename('+d.id+')" title="click to rename">'+esc(d.name)+'</td><td><select onchange="metaSetTier('+d.id+',this.value)" style="font-size:11px">'+TIERS.map(function(t){return '<option'+((d.tier||'Tier 1')===t?' selected':'')+'>'+t+'</option>';}).join('')+'</select></td><td class=r>'+Object.keys(d.cnt).length+'</td><td class="r">$'+val.toFixed(2)+'</td><td class="r">$'+toyou.toFixed(2)+'</td><td class=x onclick="metaDel('+d.id+')" title="remove">✕</td></tr>';}).join('')+'</table></div>';
  h+=grp('mdecks','Meta decks',M.length?M.length+' imported':null,imp);
  var stBody=!staples.length?'<div class=empty>Import a couple of meta decks to surface staples.</div>'
    :'<div class=tscroll><table><tr><th>Card</th><th class=r>In decks</th><th class=r>Typical</th><th class=r>Market low</th><th class=r>You own</th></tr>'+staples.slice(0,80).map(function(s){var c=BY[s.id],own=owned(s.id),need=Math.round(s.avg);
      return '<tr><td class=nm onclick="openM('+s.id+')">'+esc(c?c.n:''+s.id)+'</td><td class=r>'+s.f+'/'+M.length+'</td><td class=r>'+need+'×</td><td class="r">'+f(c?c.m:null)+'</td><td class="r" style="color:'+(own>=need?'var(--pos)':own>0?'var(--warn)':RED)+'">'+own+'</td></tr>';}).join('')+'</table></div>';
  h+=grp('mstaples','Staples across your meta decks',staples.length?staples.length+' cards':null,stBody);
  var gapBody;
  if(!M.length)gapBody='<div class=empty>Import meta decks first.</div>';
  else if(!missing.length)gapBody='<div class=ins style="border-left-color:var(--pos)">You already own every staple in your tracked meta decks. Nicely positioned.</div>';
  else gapBody='<div class=tscroll><table><tr><th>Missing staple</th><th class=r>In decks</th><th class=r>Need</th><th class=r>Unit</th><th class=r>Cost</th><th></th></tr>'+missing.map(function(s){var c=BY[s.id],need=Math.round(s.avg)-owned(s.id);
      return '<tr><td class=nm onclick="openM('+s.id+')">'+esc(c?c.n:''+s.id)+'</td><td class=r>'+s.f+'/'+M.length+'</td><td class=r>'+need+'</td><td class="r">'+f(c?c.m:null)+'</td><td class="r">'+f((c&&c.m!=null)?c.m*need:null)+'</td><td style="white-space:nowrap"><span class=addb onclick="add(\'wishlist\','+s.id+')" title="add to wishlist">+Wish</span></td></tr>';}).join('')+'</table></div>'
      +'<div class=mut style="font-size:11px;margin-top:6px">Ranked by how many of your meta decks run each card. Total to close every gap: <b>$'+missCost.toFixed(2)+'</b>.</div>';
  h+=grp('mgaps','Your gaps — staples you’re missing',missing.length?missing.length+' missing':null,gapBody);
  metaBody.innerHTML=h;}

function rarPrice(c,rs){return rs===''?(c.hr?c.rp[c.hr]:null):(rs in c.rp?c.rp[rs]:null);}
/* Five rows of filters is most of a phone screen. Only the search box stays; the rest
   folds behind one control, open on desktop where there is room. */
function toggleFilters(){var w=document.getElementById('fltwrap'),b=document.getElementById('fltbtn');
  if(!w)return; var on=w.classList.toggle('on');
  if(b)b.innerHTML=(on?'&#9652;':'&#9662;')+' Filters';}
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
/* Phones get the grid view by default — it already reflows (.grid is auto-fill), whereas the
   list table needs sideways scrolling. The ☰/▦ toggle still switches back either way. */
var listMode=(window.matchMedia&&window.matchMedia('(max-width:640px)').matches)?'grid':'list';
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
    +'<div class=gimgwrap onclick="openM('+id+')"><img class=gimg src="'+imgSrc(id)+'" onerror="this.style.display=\'none\';this.parentNode.classList.add(\'noart\')"><div class=gph>'+esc(c.n)+'</div>'
      +'<div class=gqty>×'+e.q+'</div>'+(unowned?'<div class=gneed title="you still need '+buy+'">◆'+buy+'</div>':'')+'</div>'
    +'<div class=gname onclick="openM('+id+')" title="'+eatt(c.n)+'">'+esc(c.n)+'</div>'
    +'<div class=gmeta>'+(inDeck?'<span>'+f(p)+'</span><span class=mut>own '+own+'</span>':'<input inputmode=decimal class="ovin'+(e.ov!=null?' ovset':'')+'" value="'+(e.ov!=null?e.ov:'')+'" placeholder="'+(feed!=null?feed.toFixed(2):'—')+'" onchange="setOv(\''+key+'\','+id+',this.value'+L+')" title="your price — blank uses the feed" onclick="event.stopPropagation()"><span class=mut>'+((e.cond||'')||(e.ov!=null?'yours':''))+'</span>')+'</div>'
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
    +(inDeck?'<td class="r">'+f(p)+'</td>':'<td class="r"><input inputmode=decimal class="ovin'+(e.ov!=null?' ovset':'')+'" value="'+(e.ov!=null?e.ov:'')+'" placeholder="'+(feed!=null?feed.toFixed(2):'—')+'" onchange="setOv(\''+key+'\','+id+',this.value'+L+')" title="your price — blank uses the feed price"></td>')
    +'<td class="r">'+f(p==null?null:p*(inDeck?buy:e.q))+'</td>'
    +'<td>'+extra+mv+' <span class=x onclick="del(\''+key+'\','+id+''+L+')">✕</span></td></tr>';}
function secTable(sec,label,lim,lq){var m=curDeck()[sec];var cnt=0;Object.keys(m).forEach(function(id){cnt+=m[id].q;});
  var ids=Object.keys(m).filter(function(id){var c=BY[id];return c&&(!lq||c.n.toLowerCase().indexOf(lq)>=0);});
  var over=(lim&&cnt>lim)?' <span style="color:#e0607a">(max '+lim+')</span>':'';
  var head='<h3 class=sec>'+label+' — '+cnt+' card'+(cnt===1?'':'s')+over+'</h3>';
  if(!Object.keys(m).length)return head+'<div class=empty style="padding:4px 2px">empty</div>';
  if(listMode==='grid')return head+(ids.length?'<div class=grid>'+ids.map(function(id){return gridTile(sec,id,true);}).join('')+'</div>':'<div class=empty style="padding:4px 2px">no matches</div>');
  var rows=ids.map(function(id){return listRow(sec,id,true);}).join('');
  return head+'<div class=tscroll><table><tr><th>Card</th><th>Qty</th><th class=r>Own</th><th class=r>Buy</th><th>Rarity (which you own)</th><th class=r>Unit</th><th class=r>To-buy</th><th></th></tr>'+rows+'</table></div>';}
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
  /* Long lists render in pages so a big collection doesn't build thousands of rows at once.
     listShown resets whenever the view or filter changes (see rTable's callers). */
  var shown=Math.min(D.length,listShown), more=D.length-shown;
  var V=D.slice(0,shown);
  var cnt='<div class=count>'+D.length+' line'+(D.length===1?'':'s')+' · '+total+' card'+(total===1?'':'s')
    +(more?' · <span class=mut>showing '+shown+'</span>':'')
    +' · <span class=mut>tip: edit <b>Unit</b> to your value; <b>+ver</b> adds another rarity/condition you own</span></div>';
  var moreBtn=more?'<div class=bar style="justify-content:center"><button onclick="listMore()">Show '+Math.min(more,LIST_PAGE)+' more &middot; '+more+' left</button></div>':'';
  if(listMode==='grid'){ltbl_.innerHTML=cnt+'<div class=grid>'+V.map(function(o){return gridTile(view,o.id,false,o.li);}).join('')+'</div>'+moreBtn;return;}
  var rows=V.map(function(o){return listRow(view,o.id,false,o.li);}).join('');
  ltbl_.innerHTML=cnt
    +'<div class=tscroll><table><tr><th>Card</th><th>Qty</th>'+(view==='wishlist'?'<th>Priority</th>':'')
    +'<th>Rarity</th><th>Cond.</th><th class=r>Unit (yours)</th><th class=r>Value</th><th></th></tr>'+rows+'</table></div>'
    +moreBtn;
}
var LIST_PAGE=60, listShown=LIST_PAGE;
function listMore(){listShown+=LIST_PAGE;rTable();}
function listReset(){listShown=LIST_PAGE;}
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
  mBody.innerHTML=''
    +'<img class=cimg src="'+imgSrc(c.i)+'" onerror="this.style.display=\'none\'">'
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
/* the modal had no keyboard exit; Escape closes whichever overlay is open */
addEventListener('keydown',function(e){ if(e.key!=='Escape')return;
  var ov=document.getElementById('ov');
  if(ov&&ov.style.display==='flex'){closeM();return;}
  if(typeof viewer!=='undefined'&&viewer){viewer=null;renderSim();} });
function dl(name,text,type){var b=new Blob([text],{type:type});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name;a.click();}
function exYdk(){var d=curDeck(),out=[]; [['main','#main'],['extra','#extra'],['side','!side']].forEach(function(p){out.push(p[1]);var m=d[p[0]];for(var id in m)for(var k=0;k<m[id].q;k++)out.push(id);});
  dl((St.active.replace(/[^a-z0-9]+/gi,'_')||'deck')+'.ydk',out.join('\n')+'\n','text/plain');}
function exJson(){dl('ygo_backup.json',JSON.stringify(St,null,1),'application/json');}
function imJson(ev){var fl=ev.target.files[0]; if(!fl)return; var rd=new FileReader();
  /* Writes the whole blob straight to storage and reloads, so it deliberately bypasses sv() —
     which means it also bypasses the sync hook. Mark the state dirty explicitly, or an imported
     backup would live only on this device: the pull after reload would see remote is not newer,
     find nothing dirty, and never push. The flag is in localStorage, so it survives the reload. */
  rd.onload=function(){try{var o=JSON.parse(rd.result); localStorage.setItem(KEY,JSON.stringify(o));
    if(window.syncMarkDirty)window.syncMarkDirty();
    location.reload();}catch(e){alert('Bad JSON');}}; rd.readAsText(fl);}
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
/* boot deferred until the card data is in — see the bootstrap block below */
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
</script>
<script>
/* One pass over the cards builds every index the app needs, then the UI comes up. */
function bootWith(d){
  CARDS=(d&&d.cards)||[]; SETS=(d&&d.sets)||[];
  for(var i=0;i<CARDS.length;i++){var c=CARDS[i];
    BY[c.i]=c; NAME2ID[c.n.toLowerCase()]=c.i;
    if(c.m!=null&&c.m>0)PRICED.push(c);}
  St=load();
  var l=document.getElementById('loading'); if(l)l.remove();
  kpis(); go('menu');
}
function bootFailed(e){var l=document.getElementById('loading');
  if(l)l.innerHTML='<b>Could not load card data.</b><div class=mut style="margin-top:6px;font-size:12px">'
    +String(e&&e.message||e)+' &mdash; check your connection and reload.</div>';}
__BOOTSTRAP__
</script>
<script>__SUPABASE_LIB__</script>
<script>
/* ============================ cross-device sync ============================
   Supabase, Phase 1 per SYNC_DESIGN.md: one app_state row per user, pull on
   load, debounced push on save, last-write-wins by a SERVER-owned updated_at.

   Sign-in is an emailed one-time CODE, not a clickable magic link: on iOS a link
   opens Safari, whose storage is separate from the installed PWA, so the app on
   your home screen would still be signed out. Typing the code authenticates the
   context you're actually in.

   Switched off entirely on file:// (OAuth/CORS don't work there) and when the
   build has no Supabase config — in both cases the app behaves exactly as before.
   ========================================================================== */
(function(){
var SB_URL="__SUPABASE_URL__", SB_KEY="__SUPABASE_KEY__";
var MARK_K='ygo_sync_mark', DIRTY_K='ygo_sync_dirty', EMAIL_K='ygo_sync_email';
var ready = !!(SB_URL && SB_KEY && location.protocol!=='file:' && window.supabase);
var sb = ready ? window.supabase.createClient(SB_URL,SB_KEY,
          {auth:{persistSession:true,autoRefreshToken:true,detectSessionInUrl:false}}) : null;
var user=null, status=(SB_URL&&SB_KEY)?(ready?'signedout':'off'):'unconfigured';
var msg='', pushT=null, lastSync=0, step='email', pendEmail='', busy=false;

/* --- the two markers conflict handling rests on ------------------------- */
/* mark  = the server updated_at we last adopted or wrote. Server-owned, so a
           device with a wrong clock can't corrupt sync ordering.
   dirty = local edits exist that the server has not accepted yet.          */
function markGet(){return localStorage.getItem(MARK_K)||'';}
function markSet(t){if(t)localStorage.setItem(MARK_K,t);}
function isDirty(){return localStorage.getItem(DIRTY_K)==='1';}
function setDirty(v){if(v)localStorage.setItem(DIRTY_K,'1');else localStorage.removeItem(DIRTY_K);}
function set(s,m){status=s;msg=m||'';paint();}
function paint(){
  /* the dot lives in the header, so sync state is legible from every view — it used to be
     visible only on the Home savebar */
  var d=document.getElementById('syncdot');
  if(d){var cls={idle:'ok',syncing:'busy',pending:'busy',offline:'warn',error:'warn',
                 conflict:'warn',signedout:'',off:'off',unconfigured:'off'}[status]||'';
    d.className='syncdot'+(cls?' '+cls:'');
    d.title={idle:'Synced',syncing:'Syncing…',pending:'Saving…',offline:'Offline — will sync',
             error:'Sync error — tap',conflict:'Needs your choice — tap',
             signedout:'Sign in to sync',off:'Sync off here',unconfigured:'Sync not set up'}[status]||'Sync';}
  if(typeof view!=='undefined'&&view==='menu'&&window.rMenu)rMenu();}

function stateEmpty(s){ if(!s)return true;
  var any=false,d=s.decks||{};
  for(var n in d){var x=d[n]||{};['main','extra','side'].forEach(function(k){
    if(x[k]&&Object.keys(x[k]).length)any=true;});}
  return !any && !Object.keys(s.collection||{}).length && !Object.keys(s.wishlist||{}).length
    && !(((s.bank||{}).tx)||[]).length && !(s.log||[]).length && !(s.meta||[]).length;
}
function summary(s){ s=s||{}; var d=s.decks||{},cards=0;
  for(var n in d){var x=d[n]||{};['main','extra','side'].forEach(function(k){
    var m=x[k]||{};for(var id in m)cards+=(m[id]&&m[id].q)||0;});}
  return Object.keys(d).length+' deck'+(Object.keys(d).length===1?'':'s')+' ('+cards+' cards) · '
    +Object.keys(s.collection||{}).length+' collection · '+Object.keys(s.wishlist||{}).length+' wishlist · '
    +(((s.bank||{}).tx)||[]).length+' bank · '+(s.log||[]).length+' matches';
}

/* --- push -------------------------------------------------------------- */
/* updated_at is deliberately NOT sent: the column default covers the insert and
   the trigger covers the update, then .select() returns the server's value which
   becomes our new marker. */
function pushNow(){
  if(!user||busy)return Promise.resolve();
  if(!navigator.onLine){set('offline');return Promise.resolve();}
  busy=true; set('syncing');
  return sb.from('app_state').upsert({user_id:user.id,data:St},{onConflict:'user_id'})
    .select('updated_at').single()
    .then(function(r){ busy=false;
      if(r.error){set('error',r.error.message);return;}
      markSet(r.data.updated_at); setDirty(false); lastSync=Date.now(); set('idle');
    },function(e){busy=false;set('error',String(e&&e.message||e));});
}

/* --- pull -------------------------------------------------------------- */
function pullNow(){
  if(!user||busy)return Promise.resolve();
  if(!navigator.onLine){set('offline');return Promise.resolve();}
  busy=true; set('syncing');
  return sb.from('app_state').select('data,updated_at').eq('user_id',user.id).maybeSingle()
    .then(function(r){ busy=false;
      if(r.error){set('error',r.error.message);return;}
      var remote=r.data;
      if(!remote){ return pushNow(); }              /* nothing up there yet — seed it */
      var mark=markGet();
      var remoteNewer = !mark || (new Date(remote.updated_at) > new Date(mark));
      if(!remoteNewer){ lastSync=Date.now(); set('idle'); if(isDirty())pushNow(); return; }
      /* Remote is newer. Adopting silently is only safe when this device has
         nothing unsent. Otherwise those local edits would vanish — so stop and
         ask, after writing a backup to disk first. This covers both the first
         sign-in (no marker + real local data) and the steady-state case of an
         offline edit here while another device pushed. */
      if(isDirty() || (!mark && !stateEmpty(St))){ conflict(remote); return; }
      adopt(remote);
    },function(e){busy=false;set('error',String(e&&e.message||e));});
}

function adopt(remote){
  localStorage.setItem(KEY,JSON.stringify(remote.data));
  markSet(remote.updated_at); setDirty(false);
  location.reload();                                /* same path imJson() already uses */
}

/* --- conflict: never resolve this one silently -------------------------- */
var pendingRemote=null;
function conflict(remote){
  pendingRemote=remote;
  try{ dl('ygo_backup_before_sync.json',JSON.stringify(St,null,1),'application/json'); }catch(e){}
  set('conflict');
  var b=document.getElementById('mBody'); if(!b)return;
  b.innerHTML=''
   +'<h2>Two versions to choose from</h2>'
   +'<div class=sub>This device has changes that were never synced, and the synced copy is newer. '
   +'Picking one replaces the other, so nothing is decided automatically.</div>'
   +'<div class=tx style="white-space:normal"><b>On this device</b><br>'+esc(summary(St))+'</div>'
   +'<div class=tx style="white-space:normal"><b>Synced copy</b> &middot; '+esc(fdate(String(remote.updated_at).slice(0,10)))+'<br>'+esc(summary(remote.data))+'</div>'
   +'<div class=mut style="font-size:11.5px;margin:10px 0">A backup of this device’s version has been downloaded as '
   +'<b>ygo_backup_before_sync.json</b> either way — you can re-import it from any list view.</div>'
   +'<div class=bar><button onclick="window.syncKeepMine()">Keep this device’s version</button>'
   +'<button onclick="window.syncUseRemote()">Use the synced version</button></div>';
  document.getElementById('ov').style.display='flex';
}
window.syncKeepMine=function(){ closeM(); setDirty(true); markSet(pendingRemote?pendingRemote.updated_at:'');
  pendingRemote=null; pushNow(); };                 /* our push becomes the newest write */
window.syncUseRemote=function(){ var r=pendingRemote; pendingRemote=null; closeM(); if(r)adopt(r); };

/* --- auth: emailed one-time code (length is a Supabase project setting) - */
/* Every exit path below must clear `busy` and re-render the open modal: a stuck
   busy flag would silently disable syncing for the rest of the session, and a
   message written only to the savebar is invisible while the modal covers it. */
function authFail(m){ busy=false; set('signedout',m||'Something went wrong'); syncOpen(); }
window.syncSendCode=function(){
  var el=document.getElementById('syEmail'); if(!el)return;
  var email=(el.value||'').trim(); if(!email){authFail('Enter your email first');return;}
  busy=true; set('syncing');
  sb.auth.signInWithOtp({email:email,options:{shouldCreateUser:true}}).then(function(r){
    if(r.error){authFail(r.error.message);return;}
    busy=false;
    pendEmail=email; try{localStorage.setItem(EMAIL_K,email);}catch(e){}
    step='code'; set('signedout','Code sent to '+email); syncOpen();
  },function(e){authFail(String(e&&e.message||e));});
};
window.syncVerify=function(){
  var el=document.getElementById('syCode'); if(!el)return;
  /* Supabase's OTP length is a project setting (6–10 digits), so don't hardcode it —
     just require a plausible minimum and let the server reject a wrong code. */
  var token=(el.value||'').replace(/\D/g,''); if(token.length<6){authFail('Enter the code from the email');return;}
  busy=true; set('syncing');
  sb.auth.verifyOtp({email:pendEmail,token:token,type:'email'}).then(function(r){
    if(r.error){authFail(r.error.message);return;}
    busy=false;
    user=r.data.user; step='email'; msg=''; closeM(); set('idle'); pullNow();
  },function(e){authFail(String(e&&e.message||e));});
};
window.syncSignOut=function(){ if(!sb)return; sb.auth.signOut().then(function(){
  user=null; set('signedout'); closeM(); }); };
window.syncNow=function(){ if(user)pullNow(); };
window.syncInfo=function(){ return {state:status, email:(user&&user.email)||'', last:lastSync}; };

/* --- UI ---------------------------------------------------------------- */
window.syncOpen=function(){
  var b=document.getElementById('mBody'); if(!b)return;
  var h='<h2>Sync</h2>';
  if(status==='unconfigured')
    h+='<div class=sub>This build has no Supabase project configured yet. Add the URL and anon key to <b>build_app.py</b> and rebuild.</div>';
  else if(!ready&&location.protocol==='file:')
    h+='<div class=sub>Sync is off in the local <b>file://</b> app by design — sign-in needs a real origin. Open the hosted app to sync; this copy stays offline with local card art.</div>';
  else if(user)
    h+='<div class=sub>Signed in as <b>'+esc(user.email||'')+'</b>. Your collection, decks, budget and match log sync automatically.</div>'
      +'<div class=bar><button onclick="window.syncNow()">Sync now</button><button onclick="window.syncSignOut()">Sign out</button></div>';
  else if(step==='code')
    h+='<div class=sub>Enter the code emailed to <b>'+esc(pendEmail)+'</b>.</div>'
      +'<div class=bar><input type=text id=syCode inputmode=numeric autocomplete=one-time-code maxlength=10 placeholder="code" style="width:150px;letter-spacing:.2em;text-align:center;font-size:15px">'
      +'<button onclick="window.syncVerify()">Verify</button>'
      +'<button onclick="window.syncBackToEmail()">Use a different email</button></div>';
  else
    h+='<div class=sub>Sign in to sync this device. We email you a one-time code — no password, nothing to remember.</div>'
      +'<div class=bar><input type=email id=syEmail inputmode=email autocomplete=email placeholder="you@example.com" value="'+eatt(localStorage.getItem(EMAIL_K)||'')+'" style="min-width:210px">'
      +'<button onclick="window.syncSendCode()">Email me a code</button></div>';
  if(msg)h+='<div class=mut style="font-size:11.5px;margin-top:8px">'+esc(msg)+'</div>';
  b.innerHTML=h; document.getElementById('ov').style.display='flex';
};
window.syncBackToEmail=function(){step='email';msg='';syncOpen();};

/* the chip rendered into the menu savebar */
window.syncChip=function(){
  var t={off:'Sync off',unconfigured:'Sync not set up',signedout:'Sign in to sync',
         idle:'Synced ✓',syncing:'Syncing…',pending:'Saving…',
         offline:'Offline — will sync',error:'Sync error',conflict:'Needs your choice'}[status]||'Sync';
  if(status==='idle'&&lastSync){var m=Math.round((Date.now()-lastSync)/60000);
    t='Synced ✓'+(m>0?' '+m+'m ago':' just now');}
  var col=status==='error'||status==='conflict'?'var(--dang)':status==='idle'?'var(--pos)':'var(--mut)';
  return '<span class=qlink style="color:'+col+'" onclick="syncOpen()">▸ '+t+'</span>';
};

/* --- lifecycle --------------------------------------------------------- */
window.syncTouch=function(){ if(!user)return; setDirty(true); set('pending');
  clearTimeout(pushT); pushT=setTimeout(pushNow,2500); };
/* For code paths that replace the whole state blob and immediately reload (imJson), where a
   debounced push would never get to run. The flag persists, so the pull on the next boot
   pushes it — or raises the conflict prompt if the server moved on meanwhile. */
window.syncMarkDirty=function(){ setDirty(true); };

if(ready){
  sb.auth.getSession().then(function(r){
    var s=r&&r.data&&r.data.session;
    if(s&&s.user){ user=s.user; set('idle'); pullNow(); } else set('signedout');
  });
  /* iOS kills backgrounded PWAs, which would otherwise eat whatever is still
     sitting inside the 2.5s debounce window. */
  addEventListener('visibilitychange',function(){if(document.visibilityState==='hidden'&&isDirty())pushNow();});
  addEventListener('pagehide',function(){if(isDirty())pushNow();});
  addEventListener('online',function(){if(isDirty())pushNow();else if(user)pullNow();});
  addEventListener('offline',function(){if(user)set('offline');});
}
/* This block loads after the app has already rendered the menu, so syncChip()
   didn't exist when the savebar was first built — repaint once now. */
paint();
})();
</script>
<script>/* ===== header gets out of the way on scroll =============================
   A fixed header costs its height on every screen, permanently. Hiding it as you scroll
   down and returning it the moment you scroll up gives that space back without losing
   access — the same trade x.com makes. Phone only: on desktop the space isn't scarce.
   The bottom bar deliberately stays put; it's the primary navigation.
   ======================================================================== */
(function(){
var last=0, hidden=false, TH=6, SHOW_ZONE=64;
function set(h){ if(h===hidden)return; hidden=h;
  var el=document.querySelector('header'); if(el)el.classList.toggle('hdrhide',h); }
addEventListener('scroll',function(){
  if(!window.matchMedia||!matchMedia('(max-width:900px)').matches){set(false);return;}
  var y=Math.max(0,window.scrollY);
  if(Math.abs(y-last)<TH)return;
  var down=y>last; last=y;
  if(y<SHOW_ZONE){set(false);return;}      /* near the top it's always there */
  set(down);
},{passive:true});
/* changing screen always brings it back, so you never land somewhere headerless */
window.showHeader=function(){last=0;set(false);};
})();

/* ===== edge-drag drawer =================================================
   Pulled out from the left edge, tracking your finger 1:1 the whole way — the point is that
   it feels like moving a physical thing, not like tripping a threshold that then animates
   on its own. Transitions are switched OFF while a finger is down and back ON for the
   release, so the settle is the only animated part. Where it lands is decided by velocity
   first and position second, so a quick flick opens it even from a short pull.
   ======================================================================== */
(function(){
var W=284, drag=null, open=false, el, sc;
function nodes(){el=el||document.getElementById('drawer'); sc=sc||document.getElementById('dscrim'); return !!el;}
function paint(x,anim){ if(!nodes())return;
  el.style.transition=anim?'transform .22s cubic-bezier(.22,.61,.36,1)':'none';
  sc.style.transition=anim?'opacity .22s ease':'none';
  el.style.transform='translateX('+x+'px)';
  var t=(x+W)/W;                                  /* 0 closed, 1 open */
  sc.style.opacity=Math.max(0,Math.min(1,t))*0.55;
  sc.style.pointerEvents=t>0.02?'auto':'none';
}
window.drawerOpen=function(){ if(!nodes())return; open=true; renderDrawer(); paint(0,true); };
window.drawerClose=function(){ if(!nodes())return; open=false; paint(-W,true); };
function edge(e){ return e.clientX<=26; }
addEventListener('pointerdown',function(e){
  if(e.pointerType==='mouse')return;
  if(!window.matchMedia||!matchMedia('(max-width:900px)').matches)return;
  if(!nodes())return;
  if(document.getElementById('ov')&&getComputedStyle(document.getElementById('ov')).display==='flex')return;
  if(!open&&!edge(e))return;                       /* closed: only the left edge starts a pull */
  if(open&&e.clientX>W+40)return;                  /* open: dragging back must start on it */
  if(!open)renderDrawer();
  drag={x0:e.clientX,y0:e.clientY,last:e.clientX,t:Date.now(),v:0,on:false,base:open?0:-W};
},{passive:true});
addEventListener('pointermove',function(e){
  if(!drag)return;
  var dx=e.clientX-drag.x0, dy=e.clientY-drag.y0;
  if(!drag.on){
    if(Math.abs(dy)>Math.abs(dx)&&Math.abs(dy)>12){drag=null;return;}   /* that's a scroll */
    if(Math.abs(dx)<6)return;
    drag.on=true;
  }
  var now=Date.now(), dt=Math.max(1,now-drag.t);
  drag.v=(e.clientX-drag.last)/dt;                 /* px per ms, for the release decision */
  drag.last=e.clientX; drag.t=now;
  paint(Math.max(-W,Math.min(0,drag.base+dx)),false);   /* 1:1, clamped at both ends */
});
function release(){
  if(!drag)return; var d=drag; drag=null;
  if(!d.on){ return; }
  var cur=d.base+(d.last-d.x0);
  if(Math.abs(d.v)>0.35) open=d.v>0;               /* a flick wins over position */
  else open=cur>-W/2;
  paint(open?0:-W,true);
}
addEventListener('pointerup',release);
addEventListener('pointercancel',release);
window.renderDrawer=function(){
  var box=document.getElementById('dlinks'); if(!box||typeof CARDS==='undefined')return;
  var IT=[['browse','\u{1F50D}','Browse'],['deck','\u{1F0CF}','Decks'],['collection','\u{1F4E6}','Collection'],
    ['wishlist','\u2B50','Wishlist'],['sim','\u{1F3B4}','Playtest'],['plog','\u{1F4CA}','Match log'],
    ['sets','\u{1F5C2}\uFE0F','Sets'],['meta','\u{1F9E0}','Meta'],['analytics','\u{1F4C8}','Analytics'],
    ['bank','\u{1F4B0}','Bank'],['you','\u2699\uFE0F','Profile & settings']];
  box.innerHTML=IT.map(function(i){
    return '<div class="dlink'+(typeof view!=='undefined'&&view===i[0]?' on':'')+'" onclick="drawerGo(\''+i[0]+'\')">'
      +'<span class=dico>'+i[1]+'</span><span>'+i[2]+'</span></div>';}).join('');
  var sy=(window.syncInfo?syncInfo():{email:''});
  var sub=document.getElementById('dsub');
  if(sub)sub.textContent=sy.email||'Not signed in';
  var ft=document.getElementById('dfoot');
  if(ft)ft.innerHTML='<span class=mut style="font-size:10px">build __BUILD__ &middot; snapshot __DATE__</span>';
};
window.drawerGo=function(v){ drawerClose(); setTimeout(function(){go(v);},60); };
})();

/* Sticky offsets (Browse table head, solo-board toolbar) key off --hh. The header's height
   changes with viewport width — one row on desktop, two on a phone — so measure it instead of
   hardcoding it per breakpoint, and nothing can drift out of sync. */
(function(){var hd=document.querySelector('header');if(!hd)return;
  function syncHH(){document.documentElement.style.setProperty('--hh',hd.offsetHeight+'px');}
  syncHH();
  /* Every case where the safe-area insets actually change also fires one of these: rotating
     the device, entering/leaving standalone, the in-call status bar growing. These are the
     load-bearing listeners — the observer below is only a bonus. */
  addEventListener('resize',syncHH);addEventListener('orientationchange',syncHH);
  addEventListener('load',syncHH);
  if(window.visualViewport)visualViewport.addEventListener('resize',syncHH);
  /* Cinzel loads async and changes the header's height when it swaps in. */
  if(document.fonts&&document.fonts.ready)document.fonts.ready.then(syncHH);
  /* box:'border-box' matters: the safe-area inset is PADDING, and a padding-only change
     leaves the content box identical, so a default (content-box) observer would not fire
     for the one case this is here to catch. */
  if(window.ResizeObserver)try{new ResizeObserver(syncHH).observe(hd,{box:'border-box'});}
  catch(e){new ResizeObserver(syncHH).observe(hd);}
})();
/* iOS Safari raises its own gesture events for pinch and doesn't reliably honour
   touch-action for them, so this is the layer that actually stops pinch-zoom on iPhone.
   Desktop double-click-to-select-a-word is deliberately left alone. */
['gesturestart','gesturechange','gestureend'].forEach(function(t){
  addEventListener(t,function(e){e.preventDefault();},{passive:false});
});</script>
<script>/* PWA: register the service worker only when hosted (not on file://) */
if('serviceWorker' in navigator && location.protocol!=='file:'){
  addEventListener('load',function(){navigator.serviceWorker.register('sw.js').catch(function(){});});
}</script>
</body></html>"""

if __name__ == "__main__":
    main()
