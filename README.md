# Automated Incident Triage & Alerting Tool

A Python tool that does the first five minutes of an on-call engineer's job: it scans application logs, spots incidents, looks up the matching runbook, and posts a Slack alert with next steps. Incident history is kept in SQLite so the same incident is never alerted twice.

## What it detects

| Incident | How it's detected |
|---|---|
| **Error spike** | ERRORs per minute on a service exceed both a floor (10/min) and 5× that service's median rate; consecutive hot minutes are merged into one incident |
| **Failed batch job** | A `JOB_FAILED` event, with its error code mapped to a runbook |
| **Stuck batch job** | A `JOB_START` with no success/failure after 60 minutes |

## Architecture

```
logs ──► detect.py ──► store.py (SQLite) ──► alert.py ──► Slack
         parse + 3      dedupe by             format +
         detectors      fingerprint           runbook lookup
```

## Quick start

```bash
python generate_logs.py          # creates data/app.log (~55K lines, planted incidents)
python run_triage.py             # dry run: prints alerts to the terminal
export SLACK_WEBHOOK_URL=...     # optional: send real Slack alerts
python run_triage.py
python -m unittest discover tests
```

No third-party packages: Python 3.10+ standard library only.

## Sample output

See [`sample_output/dry_run.txt`](sample_output/dry_run.txt).

## Scheduling

<!-- TODO (Thursday): add your cron line and explain it -->

## Design decisions

<!-- TODO (Friday): write 3-4 bullets in your own words. Why median instead of mean for the baseline? Why fingerprints? What would you change for a real production log volume? -->
