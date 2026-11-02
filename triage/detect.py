"""
detect.py - parse log lines and find incidents.

Three detectors:
  1. error_spike  - ERRORs per minute on a service jump well above its normal rate
  2. job_failed   - a JOB_FAILED line
  3. job_stuck    - a JOB_START with no matching end after STUCK_AFTER_MIN minutes
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median

LINE_RE = re.compile(
    r"^(?P<ts>\S+)Z\s+(?P<level>\w+)\s+svc=(?P<svc>\S+)\s+(?P<msg>.*)$"
)
KV_RE = re.compile(r"(\w+)=(\S+)")

# Tunable thresholds - talk about these in interviews (why these values?)
SPIKE_MIN_ERRORS = 10     # a minute needs at least this many errors to count
SPIKE_MULTIPLIER = 5      # ...and this many times the service's median rate
STUCK_AFTER_MIN = 60      # job with no end event after this long = stuck


@dataclass
class Incident:
    kind: str             # error_spike | job_failed | job_stuck
    service: str
    started_at: datetime
    code: str             # error code, used to pick a runbook
    summary: str
    details: dict = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """Stable ID so re-running on the same log doesn't duplicate alerts."""
        key = self.details.get("job_id") or self.started_at.strftime("%Y%m%d%H%M")
        return f"{self.kind}:{self.service}:{self.code}:{key}"


def parse_line(line):
    m = LINE_RE.match(line.strip())
    if not m:
        return None
    rec = m.groupdict()
    rec["ts"] = datetime.strptime(rec["ts"], "%Y-%m-%dT%H:%M:%S.%f")
    rec["kv"] = dict(KV_RE.findall(rec["msg"]))
    return rec


def detect(path):
    """Read the log once and return (incidents, stats)."""
    errors_per_min = defaultdict(lambda: defaultdict(int))  # svc -> minute -> count
    error_codes = defaultdict(lambda: defaultdict(int))     # (svc, minute) -> code -> count
    open_jobs = {}                                          # job_id -> start record
    incidents = []
    stats = {"lines": 0, "parsed": 0, "errors": 0, "last_ts": None}

    with open(path) as f:
        for line in f:
            stats["lines"] += 1
            rec = parse_line(line)
            if not rec:
                continue
            stats["parsed"] += 1
            stats["last_ts"] = rec["ts"]
            kv, msg, svc = rec["kv"], rec["msg"], rec["svc"]

            if msg.startswith("JOB_START"):
                open_jobs[kv["job_id"]] = rec
            elif msg.startswith("JOB_SUCCESS"):
                open_jobs.pop(kv["job_id"], None)
            elif msg.startswith("JOB_FAILED"):
                open_jobs.pop(kv["job_id"], None)
                incidents.append(Incident(
                    kind="job_failed", service=svc, started_at=rec["ts"],
                    code=kv.get("code", "UNKNOWN"),
                    summary=f"Batch job {kv['job']} failed: {msg.split(kv.get('code', ''), 1)[-1].strip()}",
                    details={"job": kv["job"], "job_id": kv["job_id"]},
                ))

            if rec["level"] == "ERROR" and not msg.startswith("JOB_FAILED"):
                stats["errors"] += 1
                minute = rec["ts"].replace(second=0, microsecond=0)
                errors_per_min[svc][minute] += 1
                error_codes[(svc, minute)][kv.get("code", "UNKNOWN")] += 1

    incidents += _find_spikes(errors_per_min, error_codes)
    incidents += _find_stuck(open_jobs, stats["last_ts"])
    incidents.sort(key=lambda i: i.started_at)
    return incidents, stats


def _find_spikes(errors_per_min, error_codes):
    spikes = []
    for svc, by_min in errors_per_min.items():
        baseline = median(by_min.values()) if by_min else 0
        threshold = max(SPIKE_MIN_ERRORS, baseline * SPIKE_MULTIPLIER)
        hot = sorted(m for m, c in by_min.items() if c >= threshold)
        # merge consecutive hot minutes into one incident
        for window in _group_consecutive(hot):
            codes = defaultdict(int)
            for m in window:
                for code, c in error_codes[(svc, m)].items():
                    codes[code] += c
            top_code = max(codes, key=codes.get)
            total = sum(by_min[m] for m in window)
            spikes.append(Incident(
                kind="error_spike", service=svc, started_at=window[0], code=top_code,
                summary=f"{total} errors in {len(window)} min on {svc} (normal ~{baseline:g}/min), mostly {top_code}",
                details={"error_count": total, "minutes": len(window),
                         "peak_per_min": max(by_min[m] for m in window)},
            ))
    return spikes


def _find_stuck(open_jobs, now):
    if now is None:
        return []
    stuck = []
    for job_id, rec in open_jobs.items():
        age = now - rec["ts"]
        if age >= timedelta(minutes=STUCK_AFTER_MIN):
            stuck.append(Incident(
                kind="job_stuck", service=rec["svc"], started_at=rec["ts"], code="STUCK_JOB",
                summary=f"Batch job {rec['kv']['job']} running {int(age.total_seconds() // 60)} min with no completion",
                details={"job": rec["kv"]["job"], "job_id": job_id},
            ))
    return stuck


def _group_consecutive(minutes):
    groups, current = [], []
    for m in minutes:
        if current and m - current[-1] > timedelta(minutes=1):
            groups.append(current)
            current = []
        current.append(m)
    if current:
        groups.append(current)
    return groups
