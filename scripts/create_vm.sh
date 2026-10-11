#!/usr/bin/env bash
# Create a GPU VM, trying zones until one has capacity.
# Usage: bash scripts/create_vm.sh NAME KIND [MAX_RUN]   (KIND: l4 | h100x1 | h100x8)
# l4 is on-demand, h100 is flex-start. The VM stops at MAX_RUN and pushes logs to the bucket on shutdown.
set -euo pipefail
NAME=$1; KIND=$2; MAX_RUN=${3:-}
cd "$(dirname "$0")/.."
FLEX=(--provisioning-model=FLEX_START --request-valid-for-duration=30m --discard-local-ssds-at-termination-timestamp=true)
case $KIND in
  l4)     TYPE=g2-standard-8; DISK=150GB;  MAX_RUN=${MAX_RUN:-4h}; PROV=(--provisioning-model=STANDARD)
          ZONES="us-central1-a us-central1-b us-central1-c us-east4-a us-east4-c" ;;
  h100x1) TYPE=a3-highgpu-1g; DISK=300GB;  MAX_RUN=${MAX_RUN:-4h}; PROV=("${FLEX[@]}")
          ZONES="us-central1-b us-central1-a us-central1-c us-east4-a us-east4-b us-east4-c" ;;
  h100x8) TYPE=a3-highgpu-8g; DISK=1000GB; MAX_RUN=${MAX_RUN:-8h}; PROV=("${FLEX[@]}")
          ZONES="us-central1-b us-central1-a us-central1-c us-east4-a us-east4-b us-east4-c" ;;
  *) echo "KIND must be l4, h100x1 or h100x8"; exit 1 ;;
esac
for z in $ZONES; do
  echo "trying $z ($TYPE, ${PROV[0]#--provisioning-model=}, max run $MAX_RUN) ..."
  if gcloud compute instances create "$NAME" --zone="$z" --machine-type="$TYPE" "${PROV[@]}" \
      --instance-termination-action=STOP --max-run-duration="$MAX_RUN" --maintenance-policy=TERMINATE \
      --image-family=common-cu129-ubuntu-2204-nvidia-580 --image-project=deeplearning-platform-release \
      --boot-disk-size="$DISK" --boot-disk-type=pd-balanced --scopes=cloud-platform \
      --metadata=install-nvidia-driver=True --metadata-from-file=shutdown-script=scripts/shutdown_sync.sh; then
    echo "ZONE=$z"; exit 0
  fi
done
echo "no capacity in any zone; try again later or another KIND"; exit 1
