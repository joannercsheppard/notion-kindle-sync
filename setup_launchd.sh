#!/usr/bin/env bash
# Generate and install a launchd agent that runs main.py at login.
# The plist is written to ~/Library/LaunchAgents/ with paths populated
# from $USER, $HOME, the current project directory, and the uv binary
# on PATH — nothing personal needs to be committed.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UV_PATH="$(command -v uv || true)"
LABEL="com.${USER}.kindle-notion-sync"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"

if [[ -z "${UV_PATH}" ]]; then
    echo "error: uv not found on PATH. Install uv first (https://github.com/astral-sh/uv)." >&2
    exit 1
fi

mkdir -p "${HOME}/Library/LaunchAgents"

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${UV_PATH}</string>
        <string>run</string>
        <string>python</string>
        <string>main.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/launchd.out.log</string>

    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/launchd.err.log</string>
</dict>
</plist>
EOF

launchctl unload "${PLIST_PATH}" 2>/dev/null || true
launchctl load "${PLIST_PATH}"

echo "Installed launchd agent: ${LABEL}"
echo "  Plist:  ${PLIST_PATH}"
echo "  Logs:   tail -f ${PROJECT_DIR}/sync.log"
echo "  Verify: launchctl list | grep kindle-notion-sync"
