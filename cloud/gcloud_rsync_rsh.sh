#!/usr/bin/env bash
# rsync -e helper. rsync passes the instance name as $1, then the remote command.
set -euo pipefail
host="$1"
shift
# Long model copies were dying ~15–20min with "Connection reset by peer".
exec gcloud compute ssh --zone="${GCP_ZONE:-us-central1-a}" "$host" \
  --ssh-flag="-o ServerAliveInterval=30" \
  --ssh-flag="-o ServerAliveCountMax=20" \
  --ssh-flag="-o TCPKeepAlive=yes" \
  -- "$@"
