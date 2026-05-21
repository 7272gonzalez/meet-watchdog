# Meet Watchdog

A lightweight macOS background agent that detects when a video call is active on your calendar and alerts you if you haven't joined. Supports Google Meet, Zoom, and Microsoft Teams. Runs every 60 seconds automatically, survives reboots, and gives up after a configurable number of alerts so it doesn't harass you if you intentionally skipped a meeting.

---

## How it works

1. Every 60 seconds, the script reads your macOS Calendar.app for meetings that have a Google Meet, Zoom, or Teams link and fall within the alert window (started recently or starting soon).
2. It checks whether Google Chrome has a tab open with that meeting's URL.
3. If no tab is found, it fires a macOS notification showing the meeting name and how many minutes ago it started, then opens the call link in Chrome.
4. Once it detects you've joined (Chrome tab is open), it marks the meeting as attended and stops alerting.
5. If you never join, it stops after `MAX_ALERTS` attempts (default: 3).

---

## Requirements

- macOS 12 or later
- Python 3 (`python3 --version` to check — install via [python.org](https://python.org) or `brew install python3`)
- Google Chrome
- Google Calendar synced to the macOS Calendar app (see setup steps below)

## Syncing Google Calendar to macOS Calendar

Meet Watchdog reads your meetings from macOS Calendar.app, so your Google Calendar must be synced to it. You do not need to use Calendar.app day-to-day — it just needs to run in the background as a data source.

One-time setup:

1. Open **System Settings → Internet Accounts**
2. Click **Add Account** and select **Google**
3. Sign in with your Google account
4. Make sure **Calendars** is checked
5. Click **Done**

Calendar.app will now stay in sync with your Google Calendar automatically. The watchdog opens it in the background as needed — you do not need to keep it open yourself.

---

## Installation

```bash
bash meet_watchdog_install.sh
```

The installer will:
- Verify Python 3 is available
- Copy `meet_watchdog.py` to `~/.meet_watchdog.py`
- Create a launchd agent at `~/Library/LaunchAgents/com.user.meetwatchdog.plist`
- Start the agent immediately

On first run, macOS will ask for two permissions — both are required:
- **Calendar access** — to read your upcoming meetings
- **Automation access for Google Chrome** — to check whether the Meet tab is open

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
- Your Google Calendar is not synced to macOS Calendar.app — go to System Settings → Internet Accounts and add your Google account with Calendar enabled.
- The meeting invite does not contain a Google Meet link in the URL, location, or description fields.
- macOS has not granted Calendar or Chrome automation permissions — go to System Settings → Privacy & Security → Automation and ensure Terminal (or whichever app runs the script) has access.
- For Zoom or Teams meetings: the watchdog detects the call link by checking Chrome for the meeting URL. If you join via the native Zoom or Teams desktop app and Chrome no longer has the tab open, the script cannot detect you as joined — `MAX_ALERTS` will limit how long it keeps alerting.

**It stopped alerting before I joined**

Either `MAX_ALERTS` was reached or the Chrome tab was briefly detected as open (e.g. the Meet link was opened but you closed the tab before the script ran again). The state is stored in `~/.meet_watchdog_state.json` — you can delete that file to reset all meeting history.

**Calendar.app keeps opening**

The script launches Calendar.app in the background when it is closed so it can query your events. Calendar.app is required to be running; if you prefer not to see it in your Dock, you can right-click its Dock icon and uncheck "Keep in Dock".

---

## Files

| File | Location | Purpose |
|------|----------|---------|
| `meet_watchdog.py` | `~/.meet_watchdog.py` | Main script |
| `com.user.meetwatchdog.plist` | `~/Library/LaunchAgents/` | launchd config — runs the script every 60s |
| `.meet_watchdog.log` | `~/` | Log output for debugging |
| `.meet_watchdog_state.json` | `~/` | Tracks alert counts and attended meetings |
