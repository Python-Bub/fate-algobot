#!/usr/bin/env bash
# Install reboot-safe paper on this GCP VM (run as the login user with sudo).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$ROOT/cloud/gcp_startup_paper.sh"
sudo cp "$ROOT/cloud/fate-algobot-paper.service" /etc/systemd/system/fate-algobot-paper.service
sudo systemctl daemon-reload
sudo systemctl enable fate-algobot-paper.service
echo "[GCP] systemd enabled: fate-algobot-paper.service (starts paper after reboot)"
echo "      paper already running is left alone — enable only, no restart."
