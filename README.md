# Meet Watchdog

A lightweight macOS background agent that detects when a video call is active on your calendar and alerts you if you haven't joined. Supports Google Meet, Zoom, and Microsoft Teams. Runs every 60 seconds automatically, survives reboots, and gives up after a configurable number of alerts so it doesn't harass you if you intentionally skipped a meeting.

---

## How it works

1. Every 60 seconds, the script calls the Google Calendar API to check for meetings with a Google Meet, Zoom, or Teams link that fall within the alert window (started recently or starting soon).
2. It checks whether Google Chrome has a tab open with that meeting's URL.
3. If no tab is found, it fires a macOS notification showing the meeting name and how many minutes ago it started, then opens the call link in Chrome.
4. Once it detects you've joined (Chrome tab is open), it marks the meeting as attended and stops alerting.
5. If you never join, it stops after `MAX_ALERTS` attempts (default: 3).

---

## Requirements

- macOS 12 or later
- Python 3 (`python3 --version` to check — install via [python.org](https://python.org) or `brew install python3`)
- Google Chrome
- A Google account with Google Calendar

---

## Google Calendar API Setup

This is a one-time setup. The watchdog reads your calendar via the Google Calendar API, which requires OAuth2 credentials from Google Cloud.

### Step 1 — Create credentials

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (top-left dropdown → **New Project**)
3. Go to **APIs & Services → Library**, search for **Google Calendar API**, and click **Enable**
4. Go to **APIs & Services → Credentials** → **Create Credentials → OAuth client ID**
5. If prompted to configure the consent screen, choose **External**, fill in an app name (e.g. "Meet Watchdog"), and save
6. For application type, select **Desktop app** and click **Create**
7. Click **Download JSON** and save the file to:
   ```
   ~/.meet_watchdog_credentials.json
   ```

### Step 2 — Authorise access

Run this once from Terminal to open a browser and grant Calendar access:

```bash
python3 ~/.meet_watchdog.py --setup
```

Sign in with your Google account and click **Allow**. A token is saved automatically and the watchdog uses it from then on. You will not need to do this again unless you revoke access.

---

## Installation

```bash
bash meet_watchdog_install.sh
```

The installer will:
- Install required Python packages (`google-auth`, `google-api-python-client`)
- Copy `meet_watchdog.py` to `~/.meet_watchdog.py`
- Create a launchd agent at `~/Library/LaunchAgents/com.user.meetwatchdog.plist`
- Run first-time Google Calendar authentication if credentials are present
- Start the agent immediately

On first run, macOS will ask for permission to control Google Chrome — accept it.

---

## Uninstall

```bash
bash meet_watchdog_uninstall.sh
```

This stops the agent and removes all installed files. Your `credentials.json` is kept in case you reinstall — delete it manually to fully revoke access.

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
- Google Calendar credentials or token are missing — run `python3 ~/.meet_watchdog.py --setup`
- The meeting invite does not contain a Google Meet, Zoom, or Teams link
- macOS has not granted Chrome automation permissions — go to System Settings → Privacy & Security → Automation and ensure Terminal has access

**It stopped alerting before I joined**

Either `MAX_ALERTS` was reached, or the Chrome tab was briefly detected as open. The state is stored in `~/.meet_watchdog_state.json` — delete that file to reset all meeting history.

**For Zoom or Teams meetings**

The watchdog detects the call link by checking Chrome for the meeting URL. If you join via the native Zoom or Teams desktop app and Chrome no longer has the tab open, the script cannot detect you as joined — `MAX_ALERTS` will limit how long it keeps alerting.

**Google token expired**

If the log shows an authentication error, re-run the setup:
```bash
python3 ~/.meet_watchdog.py --setup
```

---

## Files

| File | Location | Purpose |
|------|----------|---------|
| `meet_watchdog.py` | `~/.meet_watchdog.py` | Main script |
| `com.user.meetwatchdog.plist` | `~/Library/LaunchAgents/` | launchd config — runs the script every 60s |
| `credentials.json` | `~/.meet_watchdog_credentials.json` | Google OAuth2 client credentials |
| `token.json` | `~/.meet_watchdog_token.json` | Auto-generated auth token (do not share) |
| `.meet_watchdog.log` | `~/` | Log output for debugging |
| `.meet_watchdog_state.json` | `~/` | Tracks alert counts and attended meetings |
