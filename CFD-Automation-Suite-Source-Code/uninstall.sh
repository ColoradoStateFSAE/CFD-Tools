#!/bin/bash
# Ram Racing CFD Automation Suite -- Linux uninstaller
set -euo pipefail

INSTALL_DIR="/opt/RamRacingCFD"
LAUNCHER="/usr/local/bin/ramracingcfd"
DESKTOP_FILE="/usr/share/applications/RamRacingCFD.desktop"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR]${NC} Run as root:  sudo ./uninstall.sh"
    exit 1
fi

echo -e "${YELLOW}Removing Ram Racing CFD Automation Suite...${NC}"

rm -rf "$INSTALL_DIR"   && echo -e "${GREEN}[OK]${NC}    Removed $INSTALL_DIR"
rm -f  "$LAUNCHER"      && echo -e "${GREEN}[OK]${NC}    Removed launcher"
rm -f  "$DESKTOP_FILE"  && echo -e "${GREEN}[OK]${NC}    Removed desktop entry"

echo -e "${GREEN}Uninstall complete.${NC}"
echo "Simulation output folders were not touched."
