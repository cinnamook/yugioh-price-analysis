#!/usr/bin/env python3
"""
Daily YGO price collector -> SQLite (data/ygo.db).

Pulls the YGOPRODeck bulk endpoint (misc=yes) and appends ONE dated price row per card,
building the price history that the value-finder, tracker, and deck-planner all read from.
Card metadata is upserted each run. Stdlib only — no venv needed for the cron job.

Usage:
  python3 collect_snapshot.py                              # fetch today's snapshot from the API
  python3 collect_snapshot.py --from-file data/cardinfo_misc.json --date 2026-08-05   # seed/backfill
"""
import sqlite3, json, os, sys, argparse, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "data", "ygo.db")
API  = "https://db.ygoprodeck.com/api/v7/cardinfo.php?misc=yes"
PREMIUM = ("secret","ultimate","ghost","starlight","collector","prismatic","quarter century","platinum")
PRICE_KEYS = ["tcgplayer_price","cardmarket_price","ebay_price","amazon_price","coolstuffinc_price"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
  card_id INTEGER PRIMARY KEY, name TEXT, type TEXT, card_class TEXT, race TEXT,
  attribute TEXT, level INTEGER, atk INTEGER, def_ INTEGER, archetype TEXT,
  tcg_date TEXT, ocg_date TEXT, num_printings INTEGER, top_rarity_tier INTEGER,
  has_premium_rarity INTEGER, in_structure_deck INTEGER, ban_tcg TEXT, ban_ocg TEXT,
  first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS price_history (
  card_id INTEGER, snapshot_date TEXT,
  tcgplayer REAL, cardmarket REAL, ebay REAL, amazon REAL, coolstuffinc REAL,
  PRIMARY KEY (card_id, snapshot_date)
);
-- ready for the deck-planner phase (stay empty for now):
CREATE TABLE IF NOT EXISTS collection (card_id INTEGER, quantity INTEGER DEFAULT 1,
  condition TEXT, acquired_date TEXT, paid REAL);
CREATE TABLE IF NOT EXISTS wantlist   (card_id INTEGER, priority INTEGER DEFAULT 3, note TEXT);
CREATE INDEX IF NOT EXISTS idx_ph_date ON price_history(snapshot_date);
"""

def rtier(r):
    r=(r or "").lower()
    if any(k in r for k in ("ghost","starlight","ultimate")): return 5
    if any(k in r for k in ("secret","prismatic","collector","quarter century","platinum")): return 4
    if "ultra" in r: return 3
    if "super" in r: return 2
    if "rare" in r: return 1
    return 0
def misc(c,k):
    mi=c.get("misc_info"); return mi[0].get(k) if mi and isinstance(mi,list) else None
def fnum(x):
    try: return float(x)
    except (TypeError,ValueError): return None

def fetch():
    req=urllib.request.Request(API, headers={"User-Agent":"ygo-collector/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["data"]

def extract(c):
    sets=c.get("card_sets") or []; rars=[s.get("set_rarity") for s in sets]
    t=c.get("type",""); cls="Monster" if "Monster" in t else "Spell" if "Spell" in t else "Trap" if "Trap" in t else "Other"
    cp=c.get("card_prices"); cp=cp[0] if isinstance(cp,list) and cp else (cp if isinstance(cp,dict) else {})
    bi=c.get("banlist_info") or {}
    return dict(card_id=c["id"], name=c.get("name"), type=t, card_class=cls, race=c.get("race"),
        attribute=c.get("attribute"), level=c.get("level"), atk=c.get("atk"), def_=c.get("def"),
        archetype=c.get("archetype"), tcg_date=misc(c,"tcg_date"), ocg_date=misc(c,"ocg_date"),
        num_printings=len(sets), top_rarity_tier=max((rtier(r) for r in rars), default=0),
        has_premium_rarity=int(any(any(k in (r or "").lower() for k in PREMIUM) for r in rars)),
        in_structure_deck=int(any("structure deck" in (s.get("set_name","").lower()) for s in sets)),
        ban_tcg=bi.get("ban_tcg","Unlimited"), ban_ocg=bi.get("ban_ocg","Unlimited"),
        prices={k:fnum(cp.get(k)) for k in PRICE_KEYS})

def ingest(cards, date):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con=sqlite3.connect(DB); con.executescript(SCHEMA); cur=con.cursor()
    n_price=0
    for c in cards:
        e=extract(c)
        cur.execute("""INSERT INTO cards
            (card_id,name,type,card_class,race,attribute,level,atk,def_,archetype,tcg_date,ocg_date,
             num_printings,top_rarity_tier,has_premium_rarity,in_structure_deck,ban_tcg,ban_ocg,first_seen,last_seen)
            VALUES (:card_id,:name,:type,:card_class,:race,:attribute,:level,:atk,:def_,:archetype,:tcg_date,:ocg_date,
             :num_printings,:top_rarity_tier,:has_premium_rarity,:in_structure_deck,:ban_tcg,:ban_ocg,:d,:d)
            ON CONFLICT(card_id) DO UPDATE SET
             name=excluded.name, num_printings=excluded.num_printings, top_rarity_tier=excluded.top_rarity_tier,
             has_premium_rarity=excluded.has_premium_rarity, in_structure_deck=excluded.in_structure_deck,
             ban_tcg=excluded.ban_tcg, ban_ocg=excluded.ban_ocg, last_seen=excluded.last_seen""",
            {**{k:v for k,v in e.items() if k!="prices"}, "d":date})
        p=e["prices"]
        cur.execute("""INSERT OR REPLACE INTO price_history
            (card_id,snapshot_date,tcgplayer,cardmarket,ebay,amazon,coolstuffinc)
            VALUES (?,?,?,?,?,?,?)""",
            (e["card_id"], date, p["tcgplayer_price"], p["cardmarket_price"],
             p["ebay_price"], p["amazon_price"], p["coolstuffinc_price"]))
        n_price+=1
    con.commit()
    dates=cur.execute("SELECT COUNT(DISTINCT snapshot_date) FROM price_history").fetchone()[0]
    total=cur.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    con.close()
    print(f"[{date}] ingested {n_price} price rows | {total} cards known | {dates} snapshot date(s) in history")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--from-file"); ap.add_argument("--date")
    a=ap.parse_args()
    date = a.date or datetime.date.today().isoformat()
    cards = json.load(open(a.from_file))["data"] if a.from_file else fetch()
    ingest(cards, date)

if __name__ == "__main__":
    main()
