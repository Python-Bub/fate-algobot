#!/usr/bin/env bash
# Install reboot-safe paper + watchdog on this GCP VM (run as the login user with sudo).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(whoami)"
HOME_DIR="$(eval echo "~$USER_NAME")"
chmod +x "$ROOT/cloud/gcp_startup_paper.sh"
_install_unit() {
  local src="$1"
  local tmp
  tmp="$(mktemp)"
  sed -e "s/User=demirgenc/User=${USER_NAME}/" \
      -e "s/Group=demirgenc/Group=${USER_NAME}/" \
      -e "s|/home/demirgenc/FATE_AlgoBot|${HOME_DIR}/FATE_AlgoBot|g" \
      "$src" >"$tmp"
  sudo cp "$tmp" "/etc/systemd/system/$(basename "$src")"
  rm -f "$tmp"
}
_install_unit "$ROOT/cloud/fate-algobot-paper.service"
_install_unit "$ROOT/cloud/fate-algobot-watchdog.service"
sudo systemctl daemon-reload
sudo systemctl enable fate-algobot-paper.service
sudo systemctl enable fate-algobot-watchdog.service
echo "[GCP] systemd enabled: fate-algobot-paper.service + fate-algobot-watchdog.service"
echo "      already-running daemons are left alone — enable only, no restart."
