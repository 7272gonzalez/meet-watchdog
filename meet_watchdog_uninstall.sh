#!/bin/bash
PLIST="$HOME/Library/LaunchAgents/com.user.meetwatchdog.plist"

launchctl unload "$PLIST" 2>/dev/null && echo "Launch agent stopped." || echo "Agent was not running."
rm -f "$PLIST"                              && echo "Removed $PLIST"
rm -f "$HOME/.meet_watchdog.py"             && echo "Removed $HOME/.meet_watchdog.py"
rm -f "$HOME/.meet_watchdog.log"
rm -f "$HOME/.meet_watchdog_state.json"
echo ""
echo "Uninstall complete."
