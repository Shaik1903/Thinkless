#!/usr/bin/env bash
# GCE shutdown script: push logs and results to the bucket before the VM stops (checkpoints stay on disk).
BUCKET=${BUCKET:-thinkless-sadikh}
VM=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/name)
for d in /home/*/thinkless; do
  [ -d "$d" ] || continue
  for sub in results logs; do
    [ -d "$d/$sub" ] && timeout 20 gcloud storage rsync -r "$d/$sub" "gs://$BUCKET/shutdown/$VM/$(basename "$d")/$sub" --quiet
  done
done
