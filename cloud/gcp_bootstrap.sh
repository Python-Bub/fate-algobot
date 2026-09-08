#!/usr/bin/env bash
# GCP: training VM (SPOT) or 24/7 paper VM (STANDARD — not preemptible).
#
#   ./cloud/gcp_bootstrap.sh setup     # project + billing + Compute API check
#   ./cloud/gcp_bootstrap.sh paper     # create 24/7 paper VM (needs .env)
#   ./cloud/gcp_bootstrap.sh up        # create trainer VM, start train-everything
#   ./cloud/gcp_bootstrap.sh ssh       # SSH
#   ./cloud/gcp_bootstrap.sh status    # VM + ./run_all.sh progress
#   ./cloud/gcp_bootstrap.sh sync      # pull models + checkpoints to this Mac
#   ./cloud/gcp_bootstrap.sh sync-env  # copy local .env to the VM (secrets)
#   ./cloud/gcp_bootstrap.sh down NAME # delete that VM only (must pass the name)
#
# Do NOT chain paper && up && sync && down — down destroys the box.
#
# Prereqs: gcloud login, a project with BILLING, Compute Engine API.

set -euo pipefail
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTANCE="${GCP_INSTANCE:-fate-algobot-trainer}"
ZONE="${GCP_ZONE:-us-central1-a}"
MACHINE="${GCP_MACHINE:-n2-highmem-8}"
DISK_GB="${GCP_DISK_GB:-200}"
PROVISIONING="${GCP_PROVISIONING:-SPOT}"
REMOTE_SETUP="${GCP_REMOTE_SETUP:-cloud/gcp_remote_setup.sh}"

# macOS ships openrsync (no --info=progress2). GNU rsync on Linux is unused here.
_rsync_prog() {
  if rsync --help 2>&1 | grep -q 'info=progress2'; then
    echo --info=progress2
  else
    echo --progress
  fi
}

_require_gcp() {
  if ! command -v gcloud >/dev/null 2>&1; then
    echo "[GCP] gcloud not on PATH. brew install --cask gcloud-cli" >&2
    exit 1
  fi
  local proj
  proj="$(gcloud config get-value project 2>/dev/null || true)"
  if [ -z "$proj" ] || [ "$proj" = "(unset)" ]; then
    echo "[GCP] no project set." >&2
    echo "      gcloud config set project YOUR_PROJECT_ID" >&2
    exit 1
  fi
  local billed
  billed="$(gcloud billing projects describe "$proj" --format='value(billingEnabled)' 2>/dev/null || echo false)"
  if [ "$billed" != "True" ] && [ "$billed" != "true" ]; then
    echo "[GCP] project $proj has no billing account. Compute VMs will not start." >&2
    echo "      Open: https://console.cloud.google.com/billing?project=$proj" >&2
    echo "      Link a billing account (card; new accounts usually get \$300 credit)." >&2
    echo "      Then: ./cloud/gcp_bootstrap.sh setup" >&2
    echo "      Then: ./cloud/gcp_bootstrap.sh paper" >&2
    exit 1
  fi
}

_create_vm() {
  _require_gcp
  gcloud services enable compute.googleapis.com --quiet
  if gcloud compute instances describe "$INSTANCE" --zone="$ZONE" &>/dev/null; then
    echo "[GCP] instance $INSTANCE already exists in $ZONE."
    echo "      SSH: ./cloud/gcp_bootstrap.sh ssh"
    echo "      Destroy: ./cloud/gcp_bootstrap.sh down $INSTANCE"
    exit 1
  fi

  echo "[GCP] creating $INSTANCE  zone=$ZONE  machine=$MACHINE  disk=${DISK_GB}GB  ($PROVISIONING)…"
  local create=(gcloud compute instances create "$INSTANCE"
    --zone="$ZONE"
    --machine-type="$MACHINE"
    --image-family=ubuntu-2404-lts-amd64
    --image-project=ubuntu-os-cloud
    --boot-disk-size="${DISK_GB}GB"
    --boot-disk-type=pd-balanced)
  if [ "$PROVISIONING" = "STANDARD" ]; then
    create+=(--provisioning-model=STANDARD)
  else
    create+=(--provisioning-model=SPOT --instance-termination-action=STOP)
  fi
  create+=(--metadata=startup-script='#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3.12 python3.12-venv python3-pip git tmux htop rsync curl ca-certificates build-essential nodejs npm
touch /tmp/bootstrap.done
')
  "${create[@]}"

  echo "[GCP] waiting for SSH + apt bootstrap…"
  local ok=0
  for i in $(seq 1 60); do
    if gcloud compute ssh "$INSTANCE" --zone="$ZONE" --command="test -f /tmp/bootstrap.done" &>/dev/null; then
      ok=1
      break
    fi
    echo "  …waiting ($i/60)"
    sleep 15
  done
  if [ "$ok" != 1 ]; then
    echo "[GCP] ERROR: instance did not become ready in time." >&2
    exit 1
  fi
}

_rsync_e() {
  printf '%s' "$ROOT/cloud/gcloud_rsync_rsh.sh"
}

_prefer_running_instance() {
  if [ -n "${GCP_INSTANCE:-}" ]; then
    INSTANCE="$GCP_INSTANCE"
    return 0
  fi
  for cand in fate-algobot-paper fate-algobot-trainer; do
    if gcloud compute instances describe "$cand" --zone="$ZONE" &>/dev/null; then
      INSTANCE="$cand"
      return 0
    fi
  done
}

_sync_code() {
  echo "[GCP] rsync project → VM (excludes venv, large caches)…"
  set +e
  rsync -az --delete --partial "$(_rsync_prog)" \
    --exclude='venv/' \
    --exclude='hft/node_modules/' \
    --exclude='hft/dist/' \
    --exclude='__pycache__/' \
    --exclude='.git/' \
    --exclude='logs/' \
    --exclude='.pids/' \
    --exclude='.env' \
    --exclude='models/' \
    --exclude='data/policy/' \
    --exclude='data/cortex/' \
    --exclude='data/intel/' \
    --exclude='data/replay/' \
    --exclude='analytics/generated_patterns/' \
    -e "$(_rsync_e)" \
    "$ROOT/" "${INSTANCE}:~/FATE_AlgoBot/"
  local rc=$?
  set -e
  if [ "$rc" -eq 23 ]; then
    echo "[GCP] rsync vanished-file warning (rc=23) — code copy is enough, continuing"
    return 0
  fi
  if [ "$rc" -ne 0 ]; then
    echo "[GCP] rsync failed rc=$rc" >&2
    return "$rc"
  fi
}

_sync_env() {
  if [ ! -f "$ROOT/.env" ]; then
    echo "[GCP] no local .env — skip" >&2
    return 1
  fi
  echo "[GCP] copying .env to VM (not printed)…"
  rsync -az -e "$(_rsync_e)" \
    "$ROOT/.env" "${INSTANCE}:~/FATE_AlgoBot/.env"
}

_sync_models() {
  echo "[GCP] rsync models → VM (no --delete)…"
  rsync -az --partial "$(_rsync_prog)" \
    -e "$(_rsync_e)" \
    "$ROOT/models/" "${INSTANCE}:~/FATE_AlgoBot/models/"
}

# IAP/SSH often drops mid-copy; --partial lets the next attempt resume.
_sync_models_until_done() {
  local n=0
  local rc=0
  while true; do
    n=$((n + 1))
    echo "[GCP] models rsync attempt $n $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    set +e
    _sync_models
    rc=$?
    set -e
    if [ "$rc" -eq 0 ]; then
      echo "[GCP] models rsync complete after $n attempt(s)"
      return 0
    fi
    echo "[GCP] models rsync rc=$rc — retry in 20s (resume --partial)" >&2
    sleep 20
  done
}

cmd_setup() {
  echo "[GCP] account:  $(gcloud config get-value account 2>/dev/null)"
  echo "[GCP] project:  $(gcloud config get-value project 2>/dev/null)"
  echo "[GCP] region:   $(gcloud config get-value compute/region 2>/dev/null)"
  echo "[GCP] zone:     $(gcloud config get-value compute/zone 2>/dev/null)"
  _require_gcp
  echo "[GCP] billing OK — enabling Compute Engine API…"
  gcloud services enable compute.googleapis.com --quiet
  echo "[GCP] ready. Next (paper only — leave it running):"
  echo "      ./cloud/gcp_bootstrap.sh paper"
}

cmd_up() {
  _create_vm
  _sync_code
  echo "[GCP] remote install + start tmux training…"
  gcloud compute ssh "$INSTANCE" --zone="$ZONE" --command="chmod +x ~/FATE_AlgoBot/${REMOTE_SETUP} && bash ~/FATE_AlgoBot/${REMOTE_SETUP}"
  echo
  echo "============================================================"
  echo "  VM is up. Training runs in tmux session: train"
  echo "  SSH:        ./cloud/gcp_bootstrap.sh ssh"
  echo "  Then:       tmux attach -t train"
  echo "  Status:     ./cloud/gcp_bootstrap.sh status"
  echo "  Pull models: ./cloud/gcp_bootstrap.sh sync"
  echo "  Destroy VM: ./cloud/gcp_bootstrap.sh down $INSTANCE"
  echo "============================================================"
}

cmd_paper() {
  INSTANCE="${GCP_INSTANCE:-fate-algobot-paper}"
  MACHINE="${GCP_MACHINE:-n2-standard-4}"
  DISK_GB="${GCP_DISK_GB:-200}"
  PROVISIONING="STANDARD"
  REMOTE_SETUP="cloud/gcp_remote_paper.sh"
  _create_vm
  _sync_code
  _sync_env || {
    echo "[GCP] paper needs .env on the VM. Put it at $ROOT/.env and re-run sync-env." >&2
    exit 1
  }
  echo "[GCP] remote install + start 24/7 paper (models copy after so the book comes up)…"
  gcloud compute ssh "$INSTANCE" --zone="$ZONE" --command="chmod +x ~/FATE_AlgoBot/${REMOTE_SETUP} && bash ~/FATE_AlgoBot/${REMOTE_SETUP}"
  echo
  echo "============================================================"
  echo "  24/7 paper VM is installing. STANDARD, not SPOT."
  echo "  SSH:     GCP_INSTANCE=$INSTANCE ./cloud/gcp_bootstrap.sh ssh"
  echo "  Attach:  tmux attach -t paper"
  echo "  Stop:    ./cloud/gcp_bootstrap.sh down $INSTANCE"
  echo "============================================================"
  echo "[GCP] copying models/ (73 GB — can take hours on a home uplink; paper already running)…"
  _sync_models_until_done
}

cmd_ssh() {
  _prefer_running_instance
  exec gcloud compute ssh "$INSTANCE" --zone="$ZONE"
}

cmd_status() {
  _prefer_running_instance
  echo "[GCP] instance:"
  gcloud compute instances describe "$INSTANCE" --zone="$ZONE" \
    --format='table(name,status,machineType.basename(),scheduling.provisioningModel)' 2>/dev/null || {
    echo "  (no such instance — run ./cloud/gcp_bootstrap.sh up or paper)"; exit 1; }
  echo
  gcloud compute ssh "$INSTANCE" --zone="$ZONE" --command='cd ~/FATE_AlgoBot && ./run_all.sh progress' || true
}

cmd_sync() {
  mkdir -p "$ROOT/models" "$ROOT/data" "$ROOT/models/intraday"
  echo "[GCP] rsync models + checkpoints from VM…"
  rsync -avz --partial "$(_rsync_prog)" \
    -e "$(_rsync_e)" \
    "${INSTANCE}:~/FATE_AlgoBot/models/" "$ROOT/models/"
  rsync -avz \
    -e "$(_rsync_e)" \
    "${INSTANCE}:~/FATE_AlgoBot/data/train_checkpoint.json" "$ROOT/data/" 2>/dev/null || true
  rsync -avz \
    -e "$(_rsync_e)" \
    "${INSTANCE}:~/FATE_AlgoBot/data/intraday_train_checkpoint.json" "$ROOT/data/" 2>/dev/null || true
  echo "[GCP] local daily models: $(ls "$ROOT/models/"*_model.pkl 2>/dev/null | wc -l | tr -d ' ')"
}

cmd_sync_env() {
  INSTANCE="${GCP_INSTANCE:-fate-algobot-paper}"
  _sync_env
}

cmd_sync_models() {
  INSTANCE="${GCP_INSTANCE:-fate-algobot-paper}"
  _sync_models_until_done
}

cmd_down() {
  local name="${1:-}"
  if [ -z "$name" ]; then
    echo "[GCP] refusing to delete without an instance name." >&2
    echo "      Paper:    $0 down fate-algobot-paper" >&2
    echo "      Trainer:  $0 down fate-algobot-trainer" >&2
    exit 1
  fi
  INSTANCE="$name"
  echo "[GCP] deleting $INSTANCE in $ZONE…"
  gcloud compute instances delete "$INSTANCE" --zone="$ZONE"
  echo "[GCP] deleted $INSTANCE"
}

cmd_push_paper() {
  INSTANCE="${GCP_INSTANCE:-fate-algobot-paper}"
  _sync_code
  echo "[GCP] refresh-paper on $INSTANCE (trainers untouched)…"
  gcloud compute ssh "$INSTANCE" --zone="$ZONE" --command='cd ~/FATE_AlgoBot && PAPER_USE_FORTRESS=true PAPER_USE_LONGTERM=true ./run_all.sh refresh-paper'
}

case "${1:-}" in
  setup)    cmd_setup ;;
  up)       cmd_up ;;
  paper)    cmd_paper ;;
  ssh)      cmd_ssh ;;
  status)   cmd_status ;;
  sync)     cmd_sync ;;
  sync-env) cmd_sync_env ;;
  sync-models) cmd_sync_models ;;
  push-paper) cmd_push_paper ;;
  down)     cmd_down "${2:-${GCP_INSTANCE:-}}" ;;
  *)
    echo "Usage: $0 {setup|up|paper|ssh|status|sync|sync-env|sync-models|push-paper|down NAME}" >&2
    exit 1
    ;;
esac
