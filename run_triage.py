"""
run_triage.py - scan a log, store new incidents, alert on them.

    python run_triage.py                     # uses data/app.log
    python run_triage.py --log /var/log/x.log --db data/incidents.db
"""
import argparse
import time

from triage import alert, detect, store


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log", default="data/app.log")
    p.add_argument("--db", default="data/incidents.db")
    p.add_argument("--runbooks", default="runbooks/runbooks.json")
    args = p.parse_args()

    t0 = time.perf_counter()
    incidents, stats = detect.detect(args.log)
    conn = store.connect(args.db)
    new = store.save_new(conn, incidents)
    runbooks = alert.load_runbooks(args.runbooks)
    for inc in new:
        alert.send(alert.format_alert(inc, runbooks))
    store.log_run(conn, args.log, stats, len(new))
    elapsed = time.perf_counter() - t0

    print(f"Scanned {stats['lines']:,} lines ({stats['errors']:,} errors) in {elapsed:.2f}s")
    print(f"Found {len(incidents)} incidents, {len(new)} new (alerted), "
          f"{len(incidents) - len(new)} already known")


if __name__ == "__main__":
    main()
