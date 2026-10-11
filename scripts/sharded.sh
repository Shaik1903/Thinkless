#!/usr/bin/env bash
# Usage: scripts/sharded.sh OUT_PREFIX <generate.py args without --out/--shard>
# One generate.py per GPU, then merge shards into OUT_PREFIX.jsonl and print metrics.
set -euo pipefail
OUT=$1; shift
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT".shard*.jsonl  # stale shards from an earlier run would be merged silently
NG=$(nvidia-smi -L | wc -l)
pids=()
for i in $(seq 0 $((NG - 1))); do
  CUDA_VISIBLE_DEVICES=$i python generate.py "$@" --shard "$i" --num-shards "$NG" \
    --out "$OUT.shard$i.jsonl" > "$OUT.shard$i.log" 2>&1 &
  pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"; done
cat "$OUT".shard*.jsonl > "$OUT.jsonl"
python metrics.py "$OUT.jsonl"
