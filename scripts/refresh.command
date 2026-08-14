#!/bin/bash
# ============================================================================
#  <CYBERSE> daily refresh
#  Pulls a fresh price snapshot, checks the history is still intact, then
#  rebuilds AND publishes — so the phone app updates itself every day.
#
#  • Double-click this file any time to refresh manually, OR
#  • Point your launchd job at it (see the note at the bottom) for automation.
#
#  Your browser data (collection, decks, logs) is NOT touched by a rebuild.
#
#  WHY THE EXTRA STEPS: price history cannot be back-filled — the API only
#  serves today's prices, so a day this job doesn't run is a hole in the data
#  forever. It used to fail silently into a log nobody reads. Now anything that
#  goes wrong raises a macOS notification, and a bad day never gets published.
# ============================================================================

# Always run from the repo root (this script lives in scripts/), no matter how it's launched.
cd "$(dirname "$0")/.." || exit 1

# launchd starts with a bare PATH, so make sure the usual python homes are on it.
export PATH="/usr/local/bin:/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/bin:/bin:$PATH"
PY="$(command -v python3 || echo /usr/bin/python3)"

# A log you have to remember to read is not an alarm. This is.
notify() { /usr/bin/osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1; }

mkdir -p data
PROBLEM=""                       # set by any step that fails; drives the notification below

{
  echo ""
  echo "=========== refresh $(date) ==========="

  echo "[1/3] pulling fresh snapshot (pipeline/collect_snapshot.py) ..."
  "$PY" pipeline/collect_snapshot.py || PROBLEM="the price pull failed"

  echo "[2/3] checking the history is still complete ..."
  # Non-zero means today's row never landed — the thing we can never recover.
  if ! "$PY" pipeline/check_freshness.py; then
    [ -z "$PROBLEM" ] && PROBLEM="no fresh snapshot landed"
  fi

  echo "[3/3] rebuilding + publishing ..."
  if [ -n "$PROBLEM" ]; then
    # Don't push a day we already know is bad — it just churns the repo and
    # ships the phone a build whose data didn't actually update.
    echo "  skipping publish — fix the problem above first."
  elif git diff --quiet HEAD -- app/build_app.py; then
    bash scripts/publish.command || PROBLEM="the publish/push failed"
  else
    # publish.command commits the generator together with docs/, because docs/ is
    # generated FROM it. That invariant is what makes auto-publishing safe — but it
    # also means an unattended publish would commit whatever half-finished edit is
    # sitting in build_app.py to a public repo. So when the generator is dirty we
    # rebuild locally and stop, rather than publishing your work in progress.
    echo "  app/build_app.py has uncommitted changes — rebuilding locally, NOT publishing."
    "$PY" app/build_app.py || PROBLEM="the rebuild failed"
    [ -z "$PROBLEM" ] && PROBLEM="publish skipped: app/build_app.py has uncommitted changes"
  fi

  echo "=========== done $(date) ==========="
} >> data/collector.log 2>&1

if [ -n "$PROBLEM" ]; then
  notify "<CYBERSE> daily refresh" "$PROBLEM — see data/collector.log"
  exit 1
fi
exit 0

# ----------------------------------------------------------------------------
#  ONE-TIME SETUP for full automation
#  ----------------------------------
#  1) Make this file runnable (only needed if you'll double-click it):
#       chmod +x "$HOME/CYBERSE/scripts/refresh.command"
#
#  2) Point your existing collector job at this wrapper. Open
#       ~/Library/LaunchAgents/com.ryan.ygo-collector.plist
#     and set its ProgramArguments to:
#
#       <key>ProgramArguments</key>
#       <array>
#         <string>/bin/bash</string>
#         <string>/Users/ryannguyen/CYBERSE/scripts/refresh.command</string>
#       </array>
#
#  3) Reload the job so the change takes effect:
#       launchctl unload ~/Library/LaunchAgents/com.ryan.ygo-collector.plist
#       launchctl load   ~/Library/LaunchAgents/com.ryan.ygo-collector.plist
#
#  From then on the 1pm job pulls fresh data, rebuilds the app, and pushes it to
#  GitHub Pages automatically. Progress is logged to data/collector.log.
#
#  Pushing needs git to authenticate without a terminal. This repo uses the
#  osxkeychain helper, which works from launchd while you're logged in — but if
#  the push ever starts failing, that's the first thing to check:
#       git config --get credential.helper
# ----------------------------------------------------------------------------
