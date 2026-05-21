#!/usr/local/bin/python3
"""
meet_watchdog.py — Alerts when a video call is active but you haven't joined.
Supports Google Meet, Zoom, and Microsoft Teams.
Uses the Google Calendar API directly — no Calendar.app required.
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

STATE_FILE       = os.path.expanduser("~/.meet_watchdog_state.json")
CREDENTIALS_FILE = os.path.expanduser("~/.meet_watchdog_credentials.json")
TOKEN_FILE       = os.path.expanduser("~/.meet_watchdog_token.json")
ALERT_SOUND      = "/System/Library/Sounds/Sosumi.aiff"

ALERT_BEFORE_MINUTES = 0   # 0 = alert at start time; increase for early warnings
GRACE_PERIOD_MINUTES = 15  # stop watching this many minutes after start
MAX_ALERTS           = 3   # give up after this many alerts per meeting

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

PLATFORM_PATTERNS = {
    "Meet":  re.compile(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}"),
    "Zoom":  re.compile(r"https://(?:[\w-]+\.)?zoom\.us/j/[^\s\"'<>]+"),
    "Teams": re.compile(r"https://teams\.microsoft\.com/l/meetup-join/[^\s\"'<>]+"),
}


# ── Google Calendar API ───────────────────────────────────────────────────────

def get_calendar_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                logging.error(
                    "Credentials not found at %s. "
                    "Run: python3 ~/.meet_watchdog.py --setup",
                    CREDENTIALS_FILE,
                )
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_active_events() -> list[tuple[str, str, str, int]]:
    """Return [(title, platform, url, secs_since_start)] for active meetings."""
    try:
        service = get_calendar_service()
    except SystemExit:
        raise
    except Exception as e:
        logging.error("Failed to connect to Google Calendar API: %s", e)
        return []

    now          = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=GRACE_PERIOD_MINUTES)
    window_end   = now + timedelta(minutes=ALERT_BEFORE_MINUTES, seconds=30)

    seen_urls = set()
    events    = []

    try:
        cal_list = service.calendarList().list().execute()
        for cal in cal_list.get("items", []):
            try:
                results = service.events().list(
                    calendarId=cal["id"],
                    timeMin=window_start.isoformat(),
                    timeMax=window_end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()

                for event in results.get("items", []):
                    # Skip events the user has declined
                    is_declined = any(
                        a.get("self") and a.get("responseStatus") == "declined"
                        for a in event.get("attendees", [])
                    )
                    if is_declined:
                        continue

                    # Collect all text fields that might contain a call link
                    raw = " ".join(filter(None, [
                        event.get("hangoutLink", ""),
                        event.get("location", ""),
                        event.get("description", ""),
                    ]))
                    for ep in event.get("conferenceData", {}).get("entryPoints", []):
                        raw += " " + ep.get("uri", "")

                    for platform, pattern in PLATFORM_PATTERNS.items():
                        urls = pattern.findall(raw)
                        if urls:
                            url = urls[0]
                            if url in seen_urls:
                                break  # same event on multiple calendars
                            seen_urls.add(url)

                            start_str = event["start"].get("dateTime") or event["start"].get("date")
                            start_dt  = datetime.fromisoformat(start_str)
                            if start_dt.tzinfo is None:
                                start_dt = start_dt.replace(tzinfo=timezone.utc)
                            secs  = int((now - start_dt).total_seconds())
                            title = event.get("summary", "Untitled meeting")
                            events.append((title, platform, url, secs))
                            break

            except Exception as e:
                logging.warning("Error querying calendar %s: %s", cal.get("id"), e)

    except Exception as e:
        logging.error("Google Calendar API error: %s", e)
        return []

    if not events:
        logging.info("No active video call events found in window")
    else:
        logging.info("Found %d active event(s): %s", len(events), [t for t, *_ in events])
    return events


# ── Chrome detection ──────────────────────────────────────────────────────────

def osascript(script: str) -> tuple[str, int]:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


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


# ── Setup & main ──────────────────────────────────────────────────────────────

def setup():
    """Run the one-time OAuth flow to authenticate with Google Calendar."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"\nERROR: credentials file not found at:\n  {CREDENTIALS_FILE}\n")
        print("Follow the setup instructions in README.md to create it.")
        sys.exit(1)
    print("Opening browser for Google Calendar authentication...")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    print(f"\nAuthentication successful. Token saved to:\n  {TOKEN_FILE}\n")
    print("Meet Watchdog is now authorised to read your Google Calendar.")


def main():
    if "--setup" in sys.argv:
        setup()
        return

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
