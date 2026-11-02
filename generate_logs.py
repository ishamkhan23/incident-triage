"""
generate_logs.py - creates a realistic fake ops log with planted incidents.

Simulates one trading day across a few services. Most lines are normal
INFO noise; a few incidents are planted so the triage tool has something
to find:
  - an ERROR spike on one service (e.g. a DB connection pool exhausting)
  - batch jobs that FAIL with an error code
  - a batch job that STARTS but never finishes (stuck job)

Usage:
    python generate_logs.py                      # ~55K lines -> data/app.log
    python generate_logs.py --lines 100000 --seed 7
"""
import argparse
import random
from datetime import datetime, timedelta

SERVICES = ["confirmations", "trade-capture", "settlements", "positions", "ref-data"]
JOBS = {
    "eod_confirms": "confirmations",
    "position_snapshot": "positions",
    "settlement_batch": "settlements",
    "refdata_load": "ref-data",
}
INFO_MSGS = [
    "request handled status=200 latency_ms={lat}",
    "heartbeat ok",
    "processed message seq={seq}",
    "cache refresh complete entries={n}",
    "published event topic=trades seq={seq}",
]
WARN_MSGS = [
    "slow query latency_ms={lat}",
    "retrying downstream call attempt=2",
]
BACKGROUND_ERRORS = [
    "code=E_TIMEOUT downstream timeout after 5000ms",
    "code=E_VALIDATION trade rejected: missing counterparty",
]


def fmt(ts, level, svc, msg):
    return f"{ts.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z {level:<5} svc={svc} {msg}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lines", type=int, default=55000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="data/app.log")
    args = p.parse_args()
    rng = random.Random(args.seed)

    start = datetime(2026, 11, 2, 6, 0, 0)
    day_seconds = 14 * 3600  # 06:00 -> 20:00
    events = []

    # 1) Background noise: mostly INFO, some WARN, rare ERROR
    for i in range(args.lines):
        ts = start + timedelta(seconds=rng.uniform(0, day_seconds))
        svc = rng.choice(SERVICES)
        r = rng.random()
        if r < 0.93:
            level, msg = "INFO", rng.choice(INFO_MSGS)
        elif r < 0.995:
            level, msg = "WARN", rng.choice(WARN_MSGS)
        else:
            level, msg = "ERROR", rng.choice(BACKGROUND_ERRORS)
        msg = msg.format(lat=rng.randint(2, 900), seq=i, n=rng.randint(100, 5000))
        events.append((ts, level, svc, msg))

    # 2) Planted incident: ERROR spike on trade-capture at 10:15 for ~6 minutes
    spike_start = start.replace(hour=10, minute=15)
    for _ in range(240):
        ts = spike_start + timedelta(seconds=rng.uniform(0, 360))
        events.append((ts, "ERROR", "trade-capture",
                       "code=E_DB_POOL connection pool exhausted (max=50)"))

    # 3) Batch jobs: most succeed, two fail, one gets stuck
    job_plan = [
        ("refdata_load", 6, 30, "success"),
        ("position_snapshot", 9, 0, "success"),
        ("position_snapshot", 12, 0, "failed:E_DATA_MISMATCH position qty mismatch for 14 accounts"),
        ("settlement_batch", 13, 0, "success"),
        ("position_snapshot", 15, 0, "success"),
        ("settlement_batch", 16, 30, "stuck"),
        ("eod_confirms", 18, 0, "failed:E_FILE_MISSING counterparty file not found: cpty_confirms_20261102.csv"),
        ("refdata_load", 19, 0, "success"),
    ]
    for n, (job, hh, mm, outcome) in enumerate(job_plan, start=1):
        svc = JOBS[job]
        job_id = f"{job}-{n:03d}"
        t0 = start.replace(hour=hh, minute=mm)
        events.append((t0, "INFO", svc, f"JOB_START job={job} job_id={job_id}"))
        if outcome == "success":
            dur = rng.randint(60, 900)
            events.append((t0 + timedelta(seconds=dur), "INFO", svc,
                           f"JOB_SUCCESS job={job} job_id={job_id} duration_s={dur}"))
        elif outcome.startswith("failed:"):
            code, _, reason = outcome[len("failed:"):].partition(" ")
            dur = rng.randint(30, 300)
            events.append((t0 + timedelta(seconds=dur), "ERROR", svc,
                           f"JOB_FAILED job={job} job_id={job_id} code={code} {reason}"))
        # "stuck" -> no end event at all

    events.sort(key=lambda e: e[0])
    with open(args.out, "w") as f:
        for e in events:
            f.write(fmt(*e) + "\n")
    print(f"Wrote {len(events):,} lines to {args.out}")


if __name__ == "__main__":
    main()
