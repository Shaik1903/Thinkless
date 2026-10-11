#!/usr/bin/env bash
# Usage: scripts/sync.sh push|pull <dir>   (mirrors <dir> with gs://$BUCKET/<dir>)
set -euo pipefail
: "${BUCKET:?set BUCKET=thinkless-yourname}"
if [ "$1" = push ]; then gcloud storage rsync -r "$2" "gs://$BUCKET/$2"; else mkdir -p "$2"; gcloud storage rsync -r "gs://$BUCKET/$2" "$2"; fi
