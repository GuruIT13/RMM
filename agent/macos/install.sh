#!/bin/bash
# RMM Agent — macOS one-shot installer
# Usage: sudo bash install.sh
# Requires: macOS 12+, internet access, sudo

set -euo pipefail

INSTALL_DIR="/opt/rmm-agent"
REPO_URL="https://github.com/GuruIT13/RMM.git"
PLIST_SRC="$INSTALL_DIR/agent/macos/com.rmm.agent.plist"
PLIST_DST="/Library/LaunchDaemons/com.rmm.agent.plist"
VENV="$INSTALL_DIR/venv"
PYTHON="$VENV/bin/python3"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Run with sudo: sudo bash install.sh"
[ "$(uname)" = "Darwin" ] || fail "macOS only"

echo "=== RMM Agent macOS Installer ==="
echo ""

# ── 1. Python 3 ────────────────────────────────────────────────────────────────
echo "Checking Python 3..."
if command -v python3 &>/dev/null && python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
    PY=$(command -v python3)
    ok "Python 3 found: $PY ($(python3 --version))"
elif command -v brew &>/dev/null; then
    warn "Python 3.10+ not found — installing via Homebrew..."
    sudo -u "$SUDO_USER" brew install python@3.12
    PY=$(sudo -u "$SUDO_USER" brew --prefix python@3.12)/bin/python3
    ok "Python installed: $PY"
else
    fail "Python 3.10+ not found and Homebrew not installed.\nInstall Python from https://python.org/downloads/ then re-run."
fi

# ── 2. git ─────────────────────────────────────────────────────────────────────
echo "Checking git..."
command -v git &>/dev/null || fail "git not found. Install Xcode CLI tools: xcode-select --install"
ok "git found"

# ── 3. Clone / update repo ─────────────────────────────────────────────────────
echo "Installing to $INSTALL_DIR..."
if [ -d "$INSTALL_DIR/.git" ]; then
    warn "Existing install found — updating..."
    git -C "$INSTALL_DIR" pull --ff-only
    ok "Updated"
else
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
    ok "Cloned"
fi

# ── 4. Virtual env ─────────────────────────────────────────────────────────────
echo "Setting up Python environment..."
if [ ! -d "$VENV" ]; then
    "$PY" -m venv "$VENV"
    ok "venv created"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$INSTALL_DIR/agent/requirements-macos.txt"
ok "Dependencies installed"

# ── 5. LaunchDaemon ────────────────────────────────────────────────────────────
echo "Installing LaunchDaemon..."

# Patch plist to use correct python path (venv)
cp "$PLIST_SRC" "$PLIST_DST"

# If plist references a different python, fix it in place
/usr/libexec/PlistBuddy -c "Set :ProgramArguments:0 $PYTHON" "$PLIST_DST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :ProgramArguments:1 $INSTALL_DIR/agent/main.py" "$PLIST_DST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :WorkingDirectory $INSTALL_DIR/agent" "$PLIST_DST" 2>/dev/null || true

chown root:wheel "$PLIST_DST"
chmod 644 "$PLIST_DST"

# Unload old daemon if running
launchctl bootout system/com.rmm.agent 2>/dev/null || true

launchctl bootstrap system "$PLIST_DST"
ok "LaunchDaemon installed and started"

# ── 6. Verify ──────────────────────────────────────────────────────────────────
echo ""
sleep 2
if launchctl list | grep -q "com.rmm.agent"; then
    ok "Agent is running"
else
    warn "Agent may not have started yet — check logs:"
    warn "  tail -f /var/log/rmm-agent.log"
fi

echo ""
echo "=== Done ==="
echo "  Logs : /var/log/rmm-agent.log"
echo "  Stop : sudo launchctl bootout system/com.rmm.agent"
echo "  Start: sudo launchctl bootstrap system /Library/LaunchDaemons/com.rmm.agent.plist"
echo "  Remove: sudo bash $INSTALL_DIR/agent/macos/uninstall.sh"
