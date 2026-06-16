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

# ── 1. Homebrew (as real user, not root) ───────────────────────────────────────
REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "")}"
[ -n "$REAL_USER" ] || fail "Cannot detect real user. Run: sudo -u <username> sudo bash install.sh"

run_as_user() { sudo -Hu "$REAL_USER" env NONINTERACTIVE=1 HOMEBREW_NO_ENV_HINTS=1 "$@"; }

# Homebrew on Apple Silicon lives at /opt/homebrew, Intel at /usr/local
if [ -x "/opt/homebrew/bin/brew" ]; then
    BREW="/opt/homebrew/bin/brew"
elif [ -x "/usr/local/bin/brew" ]; then
    BREW="/usr/local/bin/brew"
else
    echo "Installing Homebrew..."
    NONINTERACTIVE=1 run_as_user bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # After install, determine path
    if [ -x "/opt/homebrew/bin/brew" ]; then
        BREW="/opt/homebrew/bin/brew"
    else
        BREW="/usr/local/bin/brew"
    fi
fi
ok "Homebrew ready: $BREW"

# ── 2. Python 3.12 via Homebrew ────────────────────────────────────────────────
echo "Checking Python..."
# Probe all known locations for python3.12 binary
BREW_PY=""
for candidate in \
    "/opt/homebrew/opt/python@3.12/libexec/bin/python3" \
    "/opt/homebrew/opt/python@3.12/bin/python3.12" \
    "/opt/homebrew/bin/python3.12" \
    "/usr/local/opt/python@3.12/libexec/bin/python3" \
    "/usr/local/opt/python@3.12/bin/python3.12" \
    "/usr/local/bin/python3.12"; do
    if [ -x "$candidate" ]; then
        BREW_PY="$candidate"
        break
    fi
done

if [ -z "$BREW_PY" ]; then
    warn "Installing python@3.12 via Homebrew..."
    run_as_user "$BREW" install --quiet python@3.12
    # Re-probe after install
    for candidate in \
        "/opt/homebrew/opt/python@3.12/libexec/bin/python3" \
        "/opt/homebrew/opt/python@3.12/bin/python3.12" \
        "/opt/homebrew/bin/python3.12"; do
        if [ -x "$candidate" ]; then
            BREW_PY="$candidate"
            break
        fi
    done
fi

[ -x "$BREW_PY" ] || { echo "ERROR: python3.12 not found — run: brew install python@3.12"; exit 1; }
PY_VERSION=$("$BREW_PY" --version 2>&1)
ok "Python: $BREW_PY ($PY_VERSION)"

# ── 3. libjpeg (Pillow build dep) ─────────────────────────────────────────────
if ! run_as_user "$BREW" list --formula jpeg &>/dev/null; then
    warn "Installing libjpeg..."
    run_as_user "$BREW" install --quiet jpeg
fi
ok "libjpeg ready"

# ── 4. git ─────────────────────────────────────────────────────────────────────
command -v git &>/dev/null || fail "git not found. Run: xcode-select --install"
ok "git ready"

# ── 5. Clone / update repo ─────────────────────────────────────────────────────
echo "Installing to $INSTALL_DIR..."
git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null || true
if [ -d "$INSTALL_DIR/.git" ]; then
    warn "Existing install found — updating..."
    git -C "$INSTALL_DIR" pull --ff-only
    ok "Updated"
else
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
    ok "Cloned"
fi

# ── 6. Virtual env + deps ─────────────────────────────────────────────────────
echo "Setting up Python environment..."
if [ ! -d "$VENV" ]; then
    "$BREW_PY" -m venv "$VENV"
    ok "venv created"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$INSTALL_DIR/agent/requirements-macos.txt"
ok "Dependencies installed"

# ── 7. LaunchDaemon ────────────────────────────────────────────────────────────
echo "Installing LaunchDaemon..."
cp "$PLIST_SRC" "$PLIST_DST"
/usr/libexec/PlistBuddy -c "Set :ProgramArguments:0 $PYTHON"                      "$PLIST_DST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :ProgramArguments:1 $INSTALL_DIR/agent/main.py"   "$PLIST_DST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :WorkingDirectory $INSTALL_DIR/agent"             "$PLIST_DST" 2>/dev/null || true
chown root:wheel "$PLIST_DST"
chmod 644 "$PLIST_DST"

launchctl bootout system/com.rmm.agent 2>/dev/null || true
launchctl bootstrap system "$PLIST_DST"
ok "LaunchDaemon installed and started"

# ── 8. Verify ──────────────────────────────────────────────────────────────────
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
echo "  Logs  : tail -f /var/log/rmm-agent.log"
echo "  Stop  : sudo launchctl bootout system/com.rmm.agent"
echo "  Start : sudo launchctl bootstrap system /Library/LaunchDaemons/com.rmm.agent.plist"
echo "  Remove: sudo bash $INSTALL_DIR/agent/macos/uninstall.sh"
