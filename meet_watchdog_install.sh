#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=$(which python3 2>/dev/null || echo "")
WATCHDOG="$HOME/.meet_watchdog.py"
PLIST="$HOME/Library/LaunchAgents/com.user.meetwatchdog.plist"
LABEL="com.user.meetwatchdog"

echo "Meet Watchdog Installer"
echo "-----------------------"

# Check requirements
if [ -z "$PYTHON" ]; then
    echo "ERROR: python3 not found. Install it from https://python.org or via Homebrew: brew install python3"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/meet_watchdog.py" ]; then
    echo "ERROR: meet_watchdog.py not found in $SCRIPT_DIR"
    echo "Make sure you are running this script from the meet-watchdog project folder."
    exit 1
fi

echo "Python:  $PYTHON ($($PYTHON --version 2>&1))"
echo "User:    $USER"
echo "Home:    $HOME"
echo ""

# Copy watchdog script
cp "$SCRIPT_DIR/meet_watchdog.py" "$WATCHDOG"
chmod +x "$WATCHDOG"
echo "Installed script -> $WATCHDOG"

# Write plist with correct paths for this user
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$WATCHDOG</string>
    </array>

    <key>StartInterval</key>
    <integer>60</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$HOME/.meet_watchdog.log</string>

    <key>StandardErrorPath</key>
    <string>$HOME/.meet_watchdog.log</string>
</dict>
</plist>
EOF
echo "Installed plist  -> $PLIST"
echo ""

# Unload existing instance if running
launchctl unload "$PLIST" 2>/dev/null || true

# Load the agent
launchctl load "$PLIST"
echo "Launch agent loaded and running."
echo ""
echo "NOTE: The watchdog reads events from macOS Calendar.app via AppleScript."
echo "Make sure Calendar.app is syncing your Google Calendar (or whichever"
echo "calendar contains your video call invites)."
echo ""
echo "To sync Google Calendar: open Calendar.app → Settings → Accounts → Add Account → Google"
echo ""
echo "Done! The watchdog will alert you every minute when a video call is active."
echo ""
echo "Useful commands:"
echo "  Stop:      launchctl unload ~/Library/LaunchAgents/com.user.meetwatchdog.plist"
echo "  Start:     launchctl load ~/Library/LaunchAgents/com.user.meetwatchdog.plist"
echo "  Logs:      tail -f ~/.meet_watchdog.log"
echo "  Uninstall: bash $SCRIPT_DIR/meet_watchdog_uninstall.sh"
echo ""
echo "To configure alert behaviour, edit ~/.meet_watchdog.py and adjust:"
echo "  ALERT_BEFORE_MINUTES  — when to start alerting (0 = at start time)"
echo "  GRACE_PERIOD_MINUTES  — how long to keep watching after start (default: 15)"
echo "  MAX_ALERTS            — max alerts before giving up (default: 3)"
