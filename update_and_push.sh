#!/bin/bash
set -e
cd "$(dirname "$0")"

python3 generate_ics.py

git add docs/

# Only commit and push if something changed
if git diff --staged --quiet; then
    echo "No changes to push."
    exit 0
fi

git -c user.name="Amsterdam Weather Bot" \
    -c user.email="bot@amsterdam-weather" \
    commit -m "Update weather forecast $(date +%Y-%m-%d)"

git push
