#!/bin/bash
# ============================================================================
#  ONE-TIME setup: make your daily 1pm job pull fresh data AND rebuild the app.
#  You only run this once. It writes the launchd job for you — no XML editing.
#  Run it with:   bash "$HOME/CYBERSE/scripts/setup_automation.command"
# ============================================================================
DIR="$HOME/CYBERSE"
PLIST="$HOME/Library/LaunchAgents/com.ryan.ygo-collector.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$DIR/data"
chmod +x "$DIR/scripts/refresh.command" 2>/dev/null

# Keep this in sync with the checked-in pipeline/com.ryan.ygo-collector.plist — the two are meant to
# be byte-identical, so `diff` between the installed job and the repo copy stays empty.
# Note: this heredoc is unquoted so $DIR expands; \$(id -u) below is escaped to stay literal.
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!-- Daily collector. Runs refresh.command, which pulls a snapshot AND rebuilds the app.

     The project deliberately lives OUTSIDE ~/Downloads: that folder is TCC-protected, and a
     launchd agent does not inherit Terminal's Full Disk Access, so bash there failed with
     "Operation not permitted" (exit 126) and the daily snapshot was silently never taken.
     Price history cannot be back-filled, so this location matters.

     Install:  cp pipeline/com.ryan.ygo-collector.plist ~/Library/LaunchAgents/
               launchctl unload ~/Library/LaunchAgents/com.ryan.ygo-collector.plist 2>/dev/null
               launchctl load   ~/Library/LaunchAgents/com.ryan.ygo-collector.plist
     Test:     launchctl kickstart -k gui/\$(id -u)/com.ryan.ygo-collector
               launchctl list | grep ygo     # second column must be 0 -->
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ryan.ygo-collector</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$DIR/scripts/refresh.command</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
  <!-- refresh.command keeps its own detailed log in data/collector.log; this catches
       anything that fails before it gets that far. -->
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
