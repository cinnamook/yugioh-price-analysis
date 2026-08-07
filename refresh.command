#!/bin/bash
# ============================================================================
#  <CYBERSE> daily refresh
#  Pulls a fresh price/printing snapshot, then rebuilds app.html — in one step.
#
#  • Double-click this file any time to refresh the app manually, OR
#  • Point your launchd job at it (see the note at the bottom) for full automation.
#
#  Your browser data (collection, decks, logs) is NOT touched by a rebuild.
# ============================================================================

# Always run from the folder this script lives in, no matter how it's launched.
cd "$(dirname "$0")" || exit 1

# launchd starts with a bare PATH, so make sure the usual python homes are on it.
export PATH="/usr/local/bin:/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/bin:/bin:$PATH"
PY="$(command -v python3 || echo /usr/bin/python3)"

mkdir -p data
{
  echo ""
  echo "=========== refresh $(date) ==========="
  echo "[1/2] pulling fresh snapshot (collect_snapshot.py) ..."
  "$PY" collect_snapshot.py
  echo "[2/2] rebuilding app (build_app.py) ..."
  "$PY" build_app.py
  echo "=========== done $(date) ==========="
} >> data/collector.log 2>&1

# ----------------------------------------------------------------------------
#  ONE-TIME SETUP for full automation
#  ----------------------------------
#  1) Make this file runnable (only needed if you'll double-click it):
#       chmod +x "$HOME/CYBERSE/refresh.command"
#
#  2) Point your existing collector job at this wrapper. Open
#       ~/Library/LaunchAgents/com.ryan.ygo-collector.plist
#     and set its ProgramArguments to:
#
#       <key>ProgramArguments</key>
#       <array>
#         <string>/bin/bash</string>
#         <string>/Users/ryannguyen/CYBERSE/refresh.command</string>
#       </array>
#
#  3) Reload the job so the change takes effect:
#       launchctl unload ~/Library/LaunchAgents/com.ryan.ygo-collector.plist
#       launchctl load   ~/Library/LaunchAgents/com.ryan.ygo-collector.plist
#
#  From then on the 1pm job pulls fresh data AND rebuilds the app automatically.
#  Progress is logged to data/collector.log.
# ----------------------------------------------------------------------------
