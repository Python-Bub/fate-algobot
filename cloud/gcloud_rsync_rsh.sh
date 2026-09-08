#!/usr/bin/env bash
# rsync -e helper. rsync passes the instance name as $1, then the remote command.
set -euo pipefail
host="$1"
shift
exec gcloud compute ssh --zone="${GCP_ZONE:-us-central1-a}" "$host" -- "$@"
