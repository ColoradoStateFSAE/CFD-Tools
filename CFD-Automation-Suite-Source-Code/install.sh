#!/bin/bash
# =============================================================================
#  Ram Racing CFD Automation Suite -- Linux installer
#  Tested on Rocky Linux 8.x and RHEL 8.x
#
#  Build the bundle first:
#      pyinstaller --clean RamRacingCFD.spec
#      sudo ./install.sh
# =============================================================================
set -euo pipefail

APP_NAME="RamRacingCFD"
INSTALL_DIR="/opt/RamRacingCFD"
LAUNCHER="/usr/local/bin/ramracingcfd"
DESKTOP_FILE="/usr/share/applications/RamRacingCFD.desktop"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE="$SCRIPT_DIR/dist/$APP_NAME"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()    { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

echo -e "${BOLD}"
echo "  Ram Racing CFD Automation Suite"
echo "  Colorado State University FSAE"
echo -e "${NC}"

[[ $EUID -eq 0 ]] || fail "Run as root:  sudo ./install.sh"

# ── Verify the bundle ────────────────────────────────────────────────────────
if [[ ! -f "$BUNDLE/$APP_NAME" ]]; then
    fail "Bundle not found at $BUNDLE/$APP_NAME
  Build it first:
      pyinstaller --clean RamRacingCFD.spec"
fi

BUNDLE_MB=$(du -sm "$BUNDLE" | cut -f1)
if [[ "$BUNDLE_MB" -lt 30 ]]; then
    fail "Bundle is only ${BUNDLE_MB} MB. Dependencies were not collected;
  rebuild with:  pyinstaller --clean RamRacingCFD.spec"
fi
info "Bundle: ${BUNDLE_MB} MB"

# ── Install ──────────────────────────────────────────────────────────────────
info "Installing to $INSTALL_DIR"
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$BUNDLE/." "$INSTALL_DIR/"
chmod -R a+rX "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/$APP_NAME"
ok "Application files installed"

# ── Launcher ─────────────────────────────────────────────────────────────────
cat > "$LAUNCHER" << 'LAUNCHEOF'
#!/bin/bash
# Ram Racing CFD launcher. Locates Ansys Fluent 2026 R1 if AWP_ROOT261 is unset.
if [[ -z "${AWP_ROOT261:-}" ]]; then
    for candidate in \
        "$HOME/ansys_inc/v261" \
        "/home/$(logname 2>/dev/null || echo nobody)/ansys_inc/v261" \
        "/ansys_inc/v261" \
        "/usr/ansys_inc/v261"; do
        if [[ -d "$candidate" ]]; then
            export AWP_ROOT261="$candidate"
            break
        fi
    done
fi

if [[ -z "${AWP_ROOT261:-}" ]]; then
    echo "WARNING: Ansys Fluent 2026 R1 not found."
    echo "Set AWP_ROOT261 before running a simulation:"
    echo "  export AWP_ROOT261=/path/to/ansys_inc/v261"
fi

exec /opt/RamRacingCFD/RamRacingCFD "$@"
LAUNCHEOF
chmod 755 "$LAUNCHER"
ok "Launcher installed at $LAUNCHER"

# ── Desktop entry ────────────────────────────────────────────────────────────
if [[ -d /usr/share/applications ]]; then
    cat > "$DESKTOP_FILE" << DESKTOPEOF
[Desktop Entry]
Name=Ram Racing CFD
Comment=Automated Ansys Fluent CFD for FSAE aerodynamics
Exec=$LAUNCHER
Icon=$INSTALL_DIR/assets/logo.png
Terminal=false
Type=Application
Categories=Science;Engineering;
StartupNotify=true
DESKTOPEOF
    ok "Desktop entry created"
fi

# ── Ansys check ──────────────────────────────────────────────────────────────
echo
info "Looking for Ansys Fluent 2026 R1"
FOUND=""
for candidate in \
    "${AWP_ROOT261:-}" \
    "/home/$(logname 2>/dev/null || echo nobody)/ansys_inc/v261" \
    "/ansys_inc/v261" \
    "/usr/ansys_inc/v261"; do
    if [[ -n "$candidate" && -d "$candidate" ]]; then
        FOUND="$candidate"
        break
    fi
done

if [[ -n "$FOUND" ]]; then
    ok "Found at $FOUND"
else
    warn "Not found. Set AWP_ROOT261 before running a simulation:"
    warn "  echo 'export AWP_ROOT261=/path/to/ansys_inc/v261' >> ~/.bashrc"
fi

# ── Qt dependency check ──────────────────────────────────────────────────────
if ! ldconfig -p 2>/dev/null | grep -q libxcb-cursor; then
    warn "libxcb-cursor is missing. The GUI will not start without it:"
    warn "  sudo dnf install xcb-util-cursor"
fi

echo
echo -e "${GREEN}${BOLD}Installation complete.${NC}"
echo
echo "  Run from a terminal:   ramracingcfd"
echo "  Or find 'Ram Racing CFD' in the application menu."
echo
