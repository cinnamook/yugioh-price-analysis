#!/bin/bash
# ============================================================================
#  ONE-TIME setup: make your daily 1pm job pull fresh data AND rebuild the app.
#  You only run this once. It writes the launchd job for you — no XML editing.
#  Run it with:   bash "$HOME/Downloads/TCG Market Analysis/setup_automation.command"
# ============================================================================
DIR="$HOME/Downloads/TCG Market Analysis"
PLIST="$HOME/Library/LaunchAgents/com.ryan.ygo-collector.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$DIR/data"
chmod +x "$DIR/refresh.command" 2>/dev/null

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ryan.ygo-collector</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$DIR/refresh.command</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$DIR/data/launchd.log</string>
  <key>StandardErrorPath</key><string>$DIR/data/launchd.log</string>
</dict>
</plist>
PLISTEOF

launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST"

echo ""
echo "  All set. Every day at 1pm (or the next time your Mac is awake), it will"
echo "  pull fresh prices/printings and rebuild the app automatically."
echo "  Job installed at: $PLIST"
echo "  Logs: $DIR/data/launchd.log  and  $DIR/data/collector.log"
echo ""
