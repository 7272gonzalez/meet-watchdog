#!/usr/local/bin/python3
"""
meet_watchdog.py — Alerts when a video call is active but you haven't joined.
Supports Google Meet, Zoom, and Microsoft Teams.
Uses macOS Calendar.app via AppleScript — no Google API credentials required.
Runs every 60s via launchd.
"""

import subprocess
import sys
import re
import json
import os
import logging
from datetime import datetime, timedelta, timezone

LOG_FILE = os.path.expanduser("~/.meet_watchdog.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

STATE_FILE  = os.path.expanduser("~/.meet_watchdog_state.json")
ALERT_SOUND = "/System/Library/Sounds/Sosumi.aiff"

ALERT_BEFORE_MINUTES = 0   # 0 = alert at start time; increase for early warnings
GRACE_PERIOD_MINUTES = 15  # stop watching this many minutes after start
MAX_ALERTS           = 3   # give up after this many alerts per meeting

PLATFORM_PATTERNS = {
    "Meet":  re.compile(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}"),
    "Zoom":  re.compile(r"https://(?:[\w-]+\.)?zoom\.us/j/[^\s\"'<>]+"),
    "Teams": re.compile(r"https://teams\.microsoft\.com/l/meetup-join/[^\s\"'<>]+"),
}


# ── Calendar.app via AppleScript ──────────────────────────────────────────────

def osascript(script: str) -> tuple[str, int]:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


def relaunch_calendar():
    """Force-quit and reopen Calendar.app to refresh its event data."""
    osascript('tell application "Calendar" to quit')
    import time
    time.sleep(2)
    osascript('tell application "Calendar" to launch')
    time.sleep(3)
    logging.info("Calendar.app relaunched to refresh events")


def ensure_calendar_running():
    """Open Calendar.app if it is not already running."""
    out, _ = osascript('tell application "Calendar" to return running')
    if out.strip().lower() != "true":
        osascript('tell application "Calendar" to launch')
        import time
        time.sleep(3)
        logging.info("Calendar.app was not running — launched it")


def get_active_events() -> list[tuple[str, str, str, int]]:
    """Return [(title, platform, url, secs_since_start)] for active meetings."""
    ensure_calendar_running()

    now          = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=GRACE_PERIOD_MINUTES)
    window_end   = now + timedelta(minutes=ALERT_BEFORE_MINUTES, seconds=30)

    # Format dates for AppleScript (local time, no timezone suffix)
    def fmt(dt: datetime) -> str:
        local = dt.astimezone()
        return local.strftime("%B %d, %Y %H:%M:%S")

    win_start_str = fmt(window_start)
    win_end_str   = fmt(window_end)

    script = f"""
set winStart to date "{win_start_str}"
set winEnd to date "{win_end_str}"
set resultLines to {{}}
tell application "Calendar"
    repeat with aCal in calendars
        set theEvents to (every event of aCal whose start date >= winStart and start date <= winEnd)
        repeat with anEvent in theEvents
            try
                set evTitle to summary of anEvent
                set evStart to start date of anEvent
                set evURL to url of anEvent
                if evURL is missing value then set evURL to ""
                set evNotes to notes of anEvent
                if evNotes is missing value then set evNotes to ""
                set evLoc to location of anEvent
                if evLoc is missing value then set evLoc to ""
                set rawData to evURL & " " & evNotes & " " & evLoc
                if rawData contains "meet.google.com" or rawData contains "zoom.us" or rawData contains "teams.microsoft.com" then
                    set secsFromEpoch to (evStart - (date "January 1, 1970 00:00:00")) - (time to GMT)
                    set resultLines to resultLines & {{evTitle & "|||" & rawData & "|||SECS~~" & secsFromEpoch}}
                end if
            end try
        end repeat
    end repeat
end tell
set AppleScript's text item delimiters to "\\n"
set output to resultLines as text
set AppleScript's text item delimiters to ""
return output
"""

    out, rc = osascript(script)
    if rc != 0 or not out.strip():
        logging.info("No active video call events found in window")
        return []

    seen_urls = set()
    events    = []

    for line in out.splitlines():
        if "|||" not in line:
            continue
        try:
            title_part, rest = line.split("|||", 1)
            raw_part, secs_part = rest.split("|||SECS~~", 1)
            title = title_part.strip()
            raw   = raw_part.strip()
            secs  = int(secs_part.strip())
            secs_since_start = int((now - datetime.fromtimestamp(secs, tz=timezone.utc)).total_seconds())
        except Exception as e:
            logging.warning("Could not parse AppleScript line %r: %s", line, e)
            continue

        for platform, pattern in PLATFORM_PATTERNS.items():
            urls = pattern.findall(raw)
            if urls:
                url = urls[0]
                if url in seen_urls:
                    break
                seen_urls.add(url)
                events.append((title, platform, url, secs_since_start))
                break

    if not events:
        logging.info("No active video call events found in window")
    else:
        logging.info("Found %d active event(s): %s", len(events), [t for t, *_ in events])
    return events


# ── Chrome detection ──────────────────────────────────────────────────────────

def is_in_call(platform: str, url: str) -> bool:
    """Return True if Chrome has a tab open matching this meeting URL."""
    if platform == "Meet":
        identifier = url.rstrip("/").split("/")[-1].split("?")[0]
    elif platform == "Zoom":
        match = re.search(r"/j/(\d+)", url)
        identifier = match.group(1) if match else "zoom.us/j"
    else:
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


# ── State ─────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


# ── Notifications ─────────────────────────────────────────────────────────────

def time_context(secs: int) -> str:
    mins = abs(secs) // 60
    if secs < 0:
        return f"starts in {mins} min" if mins > 0 else "starting now"
    return f"started {mins} min ago" if mins > 0 else "just started"


def notify(title: str, body: str):
    t = title.replace('"', '\\"')
    b = body.replace('"', '\\"')
    osascript(f'display notification "{b}" with title "{t}"')
    subprocess.run(["afplay", ALERT_SOUND])


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    events = get_active_events()
    if not events:
        sys.exit(0)

    state   = load_state()
    changed = False

    for title, platform, url, secs_since_start in events:
        entry = state.get(url, {})

        if entry == "attended":
            continue

        # Only check Chrome tab after the meeting has started
        if secs_since_start >= 0 and is_in_call(platform, url):
            logging.info("Detected in call: %s — marking as attended", title)
            state[url] = "attended"
            changed = True
            continue

        alert_count = entry.get("alerts", 0) if isinstance(entry, dict) else 0
        if alert_count >= MAX_ALERTS:
            logging.info("Max alerts (%d) reached for: %s — giving up", MAX_ALERTS, title)
            continue

        logging.info("Alerting (%d/%d) for: %s [%s] %s", alert_count + 1, MAX_ALERTS, title, platform, url)
        notify(f"Join your {platform} call!", f"{title} — {time_context(secs_since_start)}")
        subprocess.run(["open", url])
        state[url] = {"alerts": alert_count + 1}
        changed = True

    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
