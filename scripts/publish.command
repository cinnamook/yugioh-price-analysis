#!/bin/bash
# =========================================================================
#  <CYBERSE> publish — update the hosted phone app (GitHub Pages).
#
#  Rebuilds the app from your latest data, then pushes the docs/ bundle so
#  your phone's home-screen app gets the new version. Your desktop app.html
#  and your browser data (collection, decks, logs) are untouched.
#
#  Run it any time:
#    • double-click this file, OR
#    • bash "$HOME/CYBERSE/scripts/publish.command"
# =========================================================================
# This script lives in scripts/; everything below assumes the repo root.
cd "$(dirname "$0")/.." || exit 1

# launchd/Finder start with a bare PATH, so add the usual python homes.
export PATH="/usr/local/bin:/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/bin:/bin:$PATH"
PY="$(command -v python3 || echo /usr/bin/python3)"

echo "[1/3] rebuilding app + docs bundle ..."
"$PY" app/build_app.py || { echo "  build failed"; exit 1; }

echo "[2/3] committing generator + docs/ ..."
# Stage app/build_app.py alongside its output: docs/ is generated FROM it, so committing the page
# without the generator would leave the repo unable to rebuild its own live site.
git add app/build_app.py docs
git commit -m "Publish: refresh hosted app ($(date +%Y-%m-%d))" || echo "  (nothing new to commit)"

echo "[3/3] pushing to GitHub ..."
git push || { echo "  push failed — check your GitHub sign-in, then re-run."; exit 1; }

echo ""
echo "  Done. Your phone app updates the next time you open it."
echo ""
echo "  FIRST TIME ONLY — turn on hosting:"
echo "    1) github.com -> your repo (yugioh-price-analysis) -> Settings -> Pages"
echo "    2) Source: 'Deploy from a branch'  |  Branch: main  |  Folder: /docs  -> Save"
echo "    3) Wait ~1 min, then on your phone open:"
echo "         https://cinnamook.github.io/yugioh-price-analysis/"
echo "    4) iPhone: Share -> Add to Home Screen.  Android: menu -> Install app."
echo ""
