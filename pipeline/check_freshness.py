#!/usr/bin/env python3
"""
Is the price history still being collected?

Price history is the one thing in this project that CANNOT be back-filled: a day the
collector doesn't run is a hole in the data forever. The daily launchd job is therefore
a single point of failure, and until now it failed silently — a sleeping Mac, an API
change or a full disk would just stop appending rows with nothing to say so.

This is the alarm. It reads data/ygo.db and answers two questions:

  1. Is the newest snapshot recent enough?  (the collector is still running)
  2. Are there holes behind it?             (it stopped at some point and we lost days)

Exits 0 when healthy, 1 when stale — so refresh.command can shout. Stdlib only.

Usage:
  python3 pipeline/check_freshness.py                # full report
  python3 pipeline/check_freshness.py --quiet        # one line, for logs
  python3 pipeline/check_freshness.py --max-age 3    # tolerate 3 days behind
"""
import sqlite3, os, sys, argparse, datetime

HERE = os.path.dirname(os.path.abspath(__file__))         # pipeline/
ROOT = os.path.dirname(HERE)                              # repo root — data/ lives there
DB   = os.path.join(ROOT, "data", "ygo.db")

# The job runs at 1pm, so "yesterday" is normal if you look before it fires. Two days
# behind is the first genuinely suspicious state.
DEFAULT_MAX_AGE = 1


def history(con):
    """Every distinct snapshot date in the DB, ascending, as date objects."""
    rows = con.execute("SELECT DISTINCT snapshot_date FROM price_history ORDER BY 1").fetchall()
    out = []
    for (s,) in rows:
        try:
            out.append(datetime.date.fromisoformat(s))
        except (TypeError, ValueError):
            pass                                          # ignore anything malformed
    return out


def gaps(dates):
    """Calendar days missing between the first and last snapshot — permanent holes."""
    missing, have = [], set(dates)
    if not dates:
        return missing
    d, last = dates[0], dates[-1]
    while d < last:
        d += datetime.timedelta(days=1)
        if d not in have and d != last:
            missing.append(d)
    return missing


def main():
    ap = argparse.ArgumentParser(description="Check that the daily price collector is still running.")
    ap.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE,
                    help=f"days behind today before this is called stale (default {DEFAULT_MAX_AGE})")
    ap.add_argument("--quiet", action="store_true", help="one line of output, for the log")
    a = ap.parse_args()

    if not os.path.exists(DB):
        print(f"STALE: no database at {DB} — run pipeline/collect_snapshot.py")
        return 1

    con = sqlite3.connect(DB)
    try:
        dates = history(con)
        rows = con.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
    finally:
        con.close()

    if not dates:
        print("STALE: price_history is empty — run pipeline/collect_snapshot.py")
        return 1

    newest = dates[-1]
    age = (datetime.date.today() - newest).days
    stale = age > a.max_age
    holes = gaps(dates)
    verdict = "STALE" if stale else "ok"

    if a.quiet:
        print(f"{verdict}: newest snapshot {newest} ({age}d behind), "
              f"{len(dates)} days collected, {len(holes)} missing, {rows:,} rows")
        return 1 if stale else 0

    print(f"newest snapshot : {newest}  ({age} day{'' if age == 1 else 's'} behind today)")
    print(f"days collected  : {len(dates)}  ({dates[0]} → {newest})")
    print(f"price rows      : {rows:,}")

    if holes:
        # These can never be recovered, so name them rather than just counting them.
        shown = ", ".join(str(d) for d in holes[-8:])
        more = f" (+{len(holes) - 8} earlier)" if len(holes) > 8 else ""
        print(f"missing days    : {len(holes)} — {shown}{more}")
        print("                  gaps are permanent; the API only serves today's prices.")
    else:
        print("missing days    : none — unbroken history")

    if stale:
        print()
        print(f"STALE — nothing collected for {age} days. The daily job may have stopped.")
        print("  check it:  launchctl list | grep ygo-collector")
        print("  log:       tail -30 data/collector.log")
        print("  run now:   bash scripts/refresh.command")
        return 1

    print()
    print("ok — the collector is keeping up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
