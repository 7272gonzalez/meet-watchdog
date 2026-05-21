#!/usr/local/bin/python3
"""
meet_watchdog.py — Alerts when a Google Meet is active but you haven't joined.
Reads events from macOS Calendar.app (syncs Google Calendar automatically).
Runs every 60s via launchd.
"""

import subprocess
import sys
import re
import json
import os
import logging
from datetime import datetime

LOG_FILE = os.path.expanduser("~/.meet_watchdog.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

STATE_FILE = os.path.expanduser("~/.meet_watchdog_state.json")
ALERT_BEFORE_MINUTES = 2   # alert this many minutes before meeting starts
GRACE_PERIOD_MINUTES = 15  # stop alerting this many minutes after start
MAX_ALERTS = 3             # stop alerting after this many attempts per meeting
MEET_PATTERN = re.compile(r'https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}')


def osascript(script: str) -> tuple[str, int]:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


def ensure_calendar_running():
    """Launch Calendar.app in the background if it isn't already open."""
    result = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to return (name of processes) contains "Calendar"'],
        capture_output=True, text=True
    )
    if result.stdout.strip().lower() != "true":
        subprocess.run(["open", "-a", "Calendar"])
        import time; time.sleep(3)


def get_active_meet_events() -> list[tuple[str, str]]:
    """Return [(title, meet_url)] for meetings in the alert window right now."""
    before_secs = ALERT_BEFORE_MINUTES * 60
    grace_secs = GRACE_PERIOD_MINUTES * 60
    script = f"""
set output to ""
set now to current date
set windowStart to now - {grace_secs}
set windowEnd to now + {before_secs}
tell application "Calendar"
    repeat with cal in calendars
        try
            set evs to (every event of cal whose start date >= windowStart and start date <= windowEnd and end date >= now)
            repeat with ev in evs
                set evTitle to summary of ev
                set rawData to ""
                try
                    set rawData to rawData & (url of ev) & " "
                end try
                try
                    set rawData to rawData & (location of ev) & " "
                end try
                try
                    set rawData to rawData & (description of ev) & " "
                end try
                if rawData contains "meet.google.com" then
                    set output to output & evTitle & "|||" & rawData & "~~"
                end if
            end repeat
        end try
    end repeat
end tell
return output
"""
    ensure_calendar_running()
    output, code = osascript(script)
    if code != 0:
        logging.error("Calendar AppleScript failed (code %d): %s", code, output)
        return []
    logging.info("Calendar query returned: %r", output[:300] if output else "(empty)")
    events = []
    for chunk in output.split("~~"):
        if "|||" not in chunk:
            continue
        title, data = chunk.split("|||", 1)
        urls = MEET_PATTERN.findall(data)
        if urls:
            events.append((title.strip(), urls[0]))
    if not events:
        logging.info("No active Meet events found in window")
    return events


def is_in_meet(meet_url: str) -> bool:
    """Return True if Chrome has a tab open with this Meet URL."""
    code = meet_url.rstrip("/").split("/")[-1].split("?")[0]
    script = f"""
set found to false
try
    tell application "Google Chrome"
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t contains "{code}" then
                    set found to true
                end if
            end repeat
        end repeat
    end tell
end try
return found
"""
    out, _ = osascript(script)
    return out.lower() == "true"


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def notify(title: str, body: str):
    t = title.replace('"', '\\"')
    b = body.replace('"', '\\"')
    osascript(f'display notification "{b}" with title "{t}" sound name "Sosumi"')


def main():
    events = get_active_meet_events()
    if not events:
        sys.exit(0)

    state = load_state()
    changed = False

    for title, meet_url in events:
        entry = state.get(meet_url, {})

        if entry == "attended":
            continue

        if is_in_meet(meet_url):
            state[meet_url] = "attended"
            changed = True
            continue

        alert_count = entry.get("alerts", 0) if isinstance(entry, dict) else 0
        if alert_count >= MAX_ALERTS:
            logging.info("Max alerts (%d) reached for: %s — giving up", MAX_ALERTS, title)
            continue

        logging.info("Alerting (%d/%d) for: %s (%s)", alert_count + 1, MAX_ALERTS, title, meet_url)
        notify("You're late to your Google Meet!", title)
        subprocess.run(["open", meet_url])
        state[meet_url] = {"alerts": alert_count + 1}
        changed = True

    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
