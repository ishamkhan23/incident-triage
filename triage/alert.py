"""
alert.py - format incidents with runbook steps and send to Slack.

If SLACK_WEBHOOK_URL isn't set, alerts are printed instead (dry run),
so the tool works before you've made a Slack workspace.
"""
import json
import os
import urllib.request

EMOJI = {"error_spike": ":rotating_light:", "job_failed": ":x:", "job_stuck": ":hourglass:"}


def load_runbooks(path):
    with open(path) as f:
        return json.load(f)


def format_alert(inc, runbooks):
    rb = runbooks.get(inc.code, runbooks["DEFAULT"])
    steps = "\n".join(f"{n}. {s}" for n, s in enumerate(rb["steps"], 1))
    return (
        f"{EMOJI.get(inc.kind, ':warning:')} *{inc.kind.replace('_', ' ').upper()}* "
        f"on `{inc.service}` at {inc.started_at:%H:%M}\n"
        f"{inc.summary}\n"
        f"*Runbook - {rb['title']}:*\n{steps}"
    )


def send(text, webhook=None):
    webhook = webhook or os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("---- [dry run: SLACK_WEBHOOK_URL not set] ----")
        print(text)
        print()
        return False
    req = urllib.request.Request(
        webhook,
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status == 200
