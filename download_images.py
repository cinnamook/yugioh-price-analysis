#!/usr/bin/env python3
"""
Optional: download card images to data/images/<card_id>.jpg so the app shows card art.
Per the YGOPRODeck API guide, images are DOWNLOADED and re-hosted locally (never hotlinked).
Resumable — skips images already on disk — and gentle on the server. Run whenever; Ctrl-C anytime.

  python3 download_images.py              # download art for all cards (skips existing)
  python3 download_images.py --limit 500  # just the next 500 missing (do it in chunks)
"""
import sqlite3, os, time, argparse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "data", "ygo.db")
IMG  = os.path.join(HERE, "data", "images")
URL  = "https://images.ygoprodeck.com/images/cards/{}.jpg"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.08); a = ap.parse_args()
    os.makedirs(IMG, exist_ok=True)
    ids = [r[0] for r in sqlite3.connect(DB).execute("SELECT card_id FROM cards ORDER BY card_id")]
    todo = [i for i in ids if not os.path.exists(os.path.join(IMG, f"{i}.jpg"))]
    if a.limit: todo = todo[:a.limit]
    print(f"{len(ids)} cards | {len(ids)-len(todo)} already have art | downloading {len(todo)}…")
    ok = 0
    for n, cid in enumerate(todo, 1):
        try:
            req = urllib.request.Request(URL.format(cid), headers={"User-Agent": "ygo-tool/1.0"})
            data = urllib.request.urlopen(req, timeout=30).read()
            open(os.path.join(IMG, f"{cid}.jpg"), "wb").write(data); ok += 1
        except Exception as e:
            print(f"  skip {cid}: {e}")
        if n % 100 == 0: print(f"  {n}/{len(todo)} …")
        time.sleep(a.delay)          # be gentle
    print(f"done — {ok} images saved to data/images/. Re-run build_app.py to see them in the card popups.")

if __name__ == "__main__":
    main()
