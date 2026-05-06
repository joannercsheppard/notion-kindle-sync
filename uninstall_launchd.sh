#!/usr/bin/env bash
# Stop and remove the launchd agent installed by setup_launchd.sh.

set -euo pipefail

LABEL="com.${USER}.kindle-notion-sync"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"

if [[ ! -f "${PLIST_PATH}" ]]; then
    echo "Nothing to remove: ${PLIST_PATH} does not exist."
    exit 0
fi

launchctl unload "${PLIST_PATH}" 2>/dev/null || true
rm -f "${PLIST_PATH}"
echo "Removed launchd agent: ${LABEL}"
