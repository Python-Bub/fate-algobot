#!/usr/bin/env bash
# Install reboot-safe cloud-train on this GCP trainer VM (run as the login user with sudo).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(whoami)"
HOME_DIR="$(eval echo "~$USER_NAME")"
chmod +x "$ROOT/cloud/gcp_startup_train.sh"
svc="$ROOT/cloud/fate-algobot-train.service"
tmp="$(mktemp)"
sed -e "s/User=demirgenc/User=${USER_NAME}/" \
    -e "s/Group=demirgenc/Group=${USER_NAME}/" \
    -e "s|/home/demirgenc/FATE_AlgoBot|${HOME_DIR}/FATE_AlgoBot|g" \
    "$svc" >"$tmp"
sudo cp "$tmp" /etc/systemd/system/fate-algobot-train.service
rm -f "$tmp"
sudo systemctl daemon-reload
sudo systemctl enable fate-algobot-train.service
echo "[GCP] systemd enabled: fate-algobot-train.service (resumes cloud-train after Spot STOP/reboot)"
echo "      already-running trainers are left alone — enable only, no restart."
