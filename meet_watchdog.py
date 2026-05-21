#!/usr/local/bin/python3
"""
meet_watchdog.py — Alerts when a video call is active but you haven't joined.
Supports Google Meet, Zoom, and Microsoft Teams.
Reads events from macOS Calendar.app (syncs Google Calendar automatically).
Runs every 60s via launchd.
"""

import subprocess
import sys
import re
import json
import os
import logging

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
MAX_ALERTS = 3             # max alert attempts per meeting before giving up

# URL patterns for each supported platform
PLATFORM_PATTERNS = {
    "Meet":  re.compile(r'https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}'),
    "Zoom":  re.compile(r'https://(?:[\w-]+\.)?zoom\.us/j/[^\s"\'<>]+'),
    "Teams": re.compile(r'https://teams\.microsoft\.com/l/meetup-join/[^\s"\'<>]+'),
}


def osascript(script: str) -> tuple[str, int]:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


def relaunch_calendar():
    """Force-quit Calendar if running, then reopen it and wait for it to be ready."""
    import time
    osascript('tell application "Calendar" to quit')
    time.sleep(1)
    subprocess.run(["open", "-a", "Calendar"])
    time.sleep(5)


def ensure_calendar_running():
    """Launch Calendar.app in the background if it isn't already open."""
    result = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to return (name of processes) contains "Calendar"'],
        capture_output=True, text=True
    )
    if result.stdout.strip().lower() != "true":
        subprocess.run(["open", "-a", "Calendar"])
        import time; time.sleep(5)


def get_active_events() -> list[tuple[str, str, str, int]]:
    """Return [(title, platform, url, secs_since_start)] for active meetings."""
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
                if rawData contains "meet.google.com" or rawData contains "zoom.us" or rawData contains "teams.microsoft.com" then
                    set secsSinceStart to (now - start date of ev) as integer
                    set output to output & evTitle & "|||" & rawData & "|||" & secsSinceStart & "~~"
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
        logging.warning("Calendar query failed — relaunching Calendar and retrying")
        relaunch_calendar()
        output, code = osascript(script)
    if code != 0:
        logging.error("Calendar AppleScript failed after relaunch (code %d): %s", code, output)
        return []
    logging.info("Calendar query returned: %r", output[:300] if output else "(empty)")

    events = []
    for chunk in output.split("~~"):
        parts = chunk.split("|||")
        if len(parts) != 3:
            continue
        title, data, secs_str = parts
        try:
            secs_since_start = int(secs_str.strip())
        except ValueError:
            secs_since_start = 0
        for platform, pattern in PLATFORM_PATTERNS.items():
            urls = pattern.findall(data)
            if urls:
                events.append((title.strip(), platform, urls[0], secs_since_start))
                break  # one platform per event
    if not events:
        logging.info("No active video call events found in window")
    return events


def is_in_call(platform: str, url: str) -> bool:
    """Return True if Chrome has a tab open matching this meeting URL."""
    if platform == "Meet":
        identifier = url.rstrip("/").split("/")[-1].split("?")[0]
    elif platform == "Zoom":
        match = re.search(r'/j/(\d+)', url)
        identifier = match.group(1) if match else "zoom.us/j"
    else:  # Teams
        identifier = "teams.microsoft.com/l/meetup-join"

    script = f"""
set found to false
try
    tell application "Google Chrome"
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t contains "{identifier}" then
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


def time_context(secs_since_start: int) -> str:
    mins = abs(secs_since_start) // 60
    if secs_since_start < 0:
        return f"starts in {mins} min" if mins > 0 else "starting now"
    return f"started {mins} min ago" if mins > 0 else "just started"


ALERT_SOUND = "/System/Library/Sounds/Sosumi.aiff"


def notify(meeting_title: str, platform: str, secs_since_start: int):
    title = f"Join your {platform} call!"
    body = f"{meeting_title} — {time_context(secs_since_start)}"
    t = title.replace('"', '\\"')
    b = body.replace('"', '\\"')
    osascript(f'display notification "{b}" with title "{t}"')
    subprocess.run(["afplay", ALERT_SOUND])


def main():
    events = get_active_events()
    if not events:
        sys.exit(0)

    state = load_state()
    changed = False

    for title, platform, url, secs_since_start in events:
        entry = state.get(url, {})

        if entry == "attended":
            continue

        if is_in_call(platform, url):
            state[url] = "attended"
            changed = True
            continue

        alert_count = entry.get("alerts", 0) if isinstance(entry, dict) else 0
        if alert_count >= MAX_ALERTS:
            logging.info("Max alerts (%d) reached for: %s — giving up", MAX_ALERTS, title)
            continue

        logging.info("Alerting (%d/%d) for: %s [%s] %s", alert_count + 1, MAX_ALERTS, title, platform, url)
        notify(title, platform, secs_since_start)
        subprocess.run(["open", url])
        state[url] = {"alerts": alert_count + 1}
        changed = True

    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
