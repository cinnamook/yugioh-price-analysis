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

# Canonical rarities, ordered roughly ascending in collectibility. Used by the screener/planner.
RARITY_ORDER = ["Common","Foil Common","Short Print","Rare","Parallel Rare","Duel Terminal Parallel",
    "Super Rare","Ultra Rare","Secret Rare","Ultimate Rare","Ghost Rare","Gold Rare","Gold Secret Rare",
    "Platinum Rare","Platinum Secret Rare","Prismatic Secret Rare","Collector's Rare","Starlight Rare",
    "Quarter Century Secret Rare"]

def norm_rarity(raw):
    """Map one of the ~48 messy raw set_rarity strings to a canonical rarity (or None to drop junk)."""
    r = (raw or "").lower()
    if "quarter century" in r: return "Quarter Century Secret Rare"
    if "starlight" in r:       return "Starlight Rare"
    if "collector" in r:       return "Collector's Rare"
    if "prismatic" in r:       return "Prismatic Secret Rare"
    if "ghost" in r:           return "Ghost Rare"
    if "ultimate" in r:        return "Ultimate Rare"
    if "platinum" in r:        return "Platinum Secret Rare" if "secret" in r else "Platinum Rare"
    if "gold" in r:            return "Gold Secret Rare" if "secret" in r else "Gold Rare"
    if any(k in r for k in ("starfoil","shatterfoil","mosaic")): return "Foil Common"
    if "duel terminal" in r:   return "Duel Terminal Parallel"
    if "parallel" in r:        return "Parallel Rare"
    if "short print" in r:     return "Short Print"
    if "secret" in r:          return "Secret Rare"
    if "ultra" in r:           return "Ultra Rare"
    if "super" in r:           return "Super Rare"
    if r == "common" or "common" in r: return "Common"
    if "rare" in r:            return "Rare"
    return None

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
-- current per-rarity prices (rebuilt each run from card_sets; price NULL where the source has none):
CREATE TABLE IF NOT EXISTS card_rarities (
  card_id INTEGER, rarity TEXT, price REAL, n_printings INTEGER,
  PRIMARY KEY (card_id, rarity)
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

def rarity_prices(c):
    """Aggregate a card's printings into {canonical_rarity: (min_nonzero_price_or_None, n_printings)}."""
    agg = {}
    for s in (c.get("card_sets") or []):
        rar = norm_rarity(s.get("set_rarity"))
        if not rar: continue
        p = fnum(s.get("set_price"))
        cur_min, cur_n = agg.get(rar, (None, 0))
        if p and p > 0:
            cur_min = p if cur_min is None else min(cur_min, p)
        agg[rar] = (cur_min, cur_n + 1)
    return agg

def ingest(cards, date):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con=sqlite3.connect(DB); con.executescript(SCHEMA); cur=con.cursor()
    cur.execute("DELETE FROM card_rarities")     # per-rarity table reflects the current snapshot
    n_price=0
    for c in cards:
        e=extract(c)
        for rar, (pr, n) in rarity_prices(c).items():
            cur.execute("INSERT OR REPLACE INTO card_rarities (card_id,rarity,price,n_printings) VALUES (?,?,?,?)",
                        (e["card_id"], rar, pr, n))
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
