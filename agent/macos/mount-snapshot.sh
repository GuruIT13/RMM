#!/bin/bash
# Mount SMB snapshot share for RMM Agent
# Usage: sudo bash mount-snapshot.sh
# Edit SMB_* variables below to change server/credentials

SMB_SERVER="192.168.78.37"
SMB_SHARE="snapshots"
SMB_USER="Guruit"
SMB_PASS="123456"
MOUNT_POINT="/Volumes/rmm-snapshots"

# ── Mount ──────────────────────────────────────────────────────────────────────
mkdir -p "$MOUNT_POINT"

# Unmount first if already mounted
if mount | grep -q "$MOUNT_POINT"; then
    umount "$MOUNT_POINT" 2>/dev/null || diskutil unmount force "$MOUNT_POINT" 2>/dev/null
fi

mount_smbfs -o nobrowse "//${SMB_USER}:${SMB_PASS}@${SMB_SERVER}/${SMB_SHARE}" "$MOUNT_POINT"

if [ $? -eq 0 ]; then
    echo "✓ Mounted at $MOUNT_POINT"
else
    echo "✗ Mount failed — check server/credentials"
    exit 1
fi

# ── Auto-mount on boot via LaunchDaemon ───────────────────────────────────────
PLIST="/Library/LaunchDaemons/com.rmm.mount-snapshot.plist"

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.rmm.mount-snapshot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>mkdir -p ${MOUNT_POINT} &amp;&amp; mount_smbfs -o nobrowse //${SMB_USER}:${SMB_PASS}@${SMB_SERVER}/${SMB_SHARE} ${MOUNT_POINT}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/rmm-mount.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/rmm-mount-error.log</string>
</dict>
</plist>
EOF

chown root:wheel "$PLIST"
chmod 644 "$PLIST"
launchctl bootout system/com.rmm.mount-snapshot 2>/dev/null || true
launchctl bootstrap system "$PLIST"

echo "✓ Auto-mount on boot configured"
echo ""
echo "Share path to use in Dashboard: $MOUNT_POINT"
echo ""
echo "To change server/credentials later: edit $0 and re-run"
