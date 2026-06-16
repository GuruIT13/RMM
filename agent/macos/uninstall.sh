#!/bin/bash
# RMM Agent — macOS uninstaller
# Usage: sudo bash uninstall.sh

set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo"; exit 1; }

echo "=== RMM Agent Uninstaller ==="

launchctl bootout system/com.rmm.agent 2>/dev/null && echo "✓ Daemon stopped" || echo "! Daemon was not running"
rm -f /Library/LaunchDaemons/com.rmm.agent.plist && echo "✓ LaunchDaemon removed"
rm -rf /opt/rmm-agent && echo "✓ Files removed"
rm -f /var/log/rmm-agent.log /var/log/rmm-agent-error.log && echo "✓ Logs removed"

echo "Done."
