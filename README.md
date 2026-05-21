# Meet Watchdog

A lightweight macOS background agent that detects when a video call is active on your calendar and alerts you if you haven't joined. Supports Google Meet, Zoom, and Microsoft Teams. Runs every 60 seconds automatically, survives reboots, and gives up after a configurable number of alerts so it doesn't harass you if you intentionally skipped a meeting.

---

## How it works

1. Every 60 seconds, the script reads macOS Calendar.app via AppleScript to check for meetings with a Google Meet, Zoom, or Teams link that fall within the alert window (started recently or starting soon).
2. It checks whether Google Chrome has a tab open with that meeting's URL.
3. If no tab is found, it fires a macOS notification showing the meeting name and how many minutes ago it started, then opens the call link in Chrome.
4. Once it detects you've joined (Chrome tab is open), it marks the meeting as attended and stops alerting.
5. If you never join, it stops after `MAX_ALERTS` attempts (default: 3).

---

## Requirements

- macOS 12 or later
- Python 3 (`python3 --version` to check — install via [python.org](https://python.org) or `brew install python3`)
- Google Chrome
- macOS Calendar.app with your calendar accounts synced

---

## Syncing Google Calendar to macOS Calendar

The watchdog reads events from Calendar.app via AppleScript, so your Google Calendar (or any other calendar with your video call invites) must be synced there first.

**To add your Google account:**

1. Open **Calendar.app**
2. Go to **Calendar → Settings → Accounts** (or **Preferences → Accounts** on older macOS)
3. Click **+** and choose **Google**
4. Sign in with your Google account

Once added, Calendar.app will keep your events in sync automatically. No credentials or API keys are required by the watchdog itself.

---

## Installation

```bash
bash meet_watchdog_install.sh
```

The installer will:
- Copy `meet_watchdog.py` to `~/.meet_watchdog.py`
- Create a launchd agent at `~/Library/LaunchAgents/com.user.meetwatchdog.plist`
- Start the agent immediately

On first run, macOS will ask for permission to control Google Chrome and read Calendar — accept both.

---

## Uninstall

```bash
bash meet_watchdog_uninstall.sh
```

This stops the agent and removes all installed files.

---

## Managing the agent

| Action | Command |
|--------|---------|
| Stop | `launchctl unload ~/Library/LaunchAgents/com.user.meetwatchdog.plist` |
| Start | `launchctl load ~/Library/LaunchAgents/com.user.meetwatchdog.plist` |
| Check status | `launchctl list \| grep meetwatchdog` |
| View logs | `tail -f ~/.meet_watchdog.log` |

---

## Configuration

Open `~/.meet_watchdog.py` in a text editor and adjust these constants near the top of the file:

| Setting | Default | Description |
|---------|---------|-------------|
| `ALERT_BEFORE_MINUTES` | `0` | How many minutes before start time to begin alerting. `0` = alert exactly at start time, `2` = alert 2 minutes early, etc. |
| `GRACE_PERIOD_MINUTES` | `15` | How many minutes after a meeting starts to keep watching it |
| `MAX_ALERTS` | `3` | Maximum number of alert/open attempts per meeting before giving up |

**When should I get alerted?**

| `ALERT_BEFORE_MINUTES` | Behaviour |
|---|---|
| `0` | Alert fires exactly at the meeting start time ← default |
| `2` | Alert fires 2 minutes before the meeting starts |
| `5` | Alert fires 5 minutes before the meeting starts |

Changes take effect on the next 60-second tick — no restart needed.

---

## Troubleshooting

**No alerts are firing**

Check the log for errors:
```bash
cat ~/.meet_watchdog.log
```

Common causes:
- Calendar.app is not running or not synced — open Calendar.app and wait for it to sync
- The meeting invite does not contain a Google Meet, Zoom, or Teams link
- macOS has not granted Chrome automation permissions — go to System Settings → Privacy & Security → Automation and ensure Terminal has access

**It stopped alerting before I joined**

Either `MAX_ALERTS` was reached, or the Chrome tab was briefly detected as open. The state is stored in `~/.meet_watchdog_state.json` — delete that file to reset all meeting history.

**For Zoom or Teams meetings**

The watchdog detects the call link by checking Chrome for the meeting URL. If you join via the native Zoom or Teams desktop app and Chrome no longer has the tab open, the script cannot detect you as joined — `MAX_ALERTS` will limit how long it keeps alerting.

---

## Files

| File | Location | Purpose |
|------|----------|---------|
| `meet_watchdog.py` | `~/.meet_watchdog.py` | Main script |
| `com.user.meetwatchdog.plist` | `~/Library/LaunchAgents/` | launchd config — runs the script every 60s |
| `.meet_watchdog.log` | `~/` | Log output for debugging |
| `.meet_watchdog_state.json` | `~/` | Tracks alert counts and attended meetings |
