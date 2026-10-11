#!/usr/bin/env bash
# Serving benchmark: one vLLM server per GPU, all configs in parallel. Log: logs/serve.log
# Usage: bash scripts/serve_bench.sh   (NO_SHUTDOWN=1 keeps the VM running afterwards)
set -uo pipefail
cd ~/thinkless
set -a; . ./.env; set +a
export BUCKET=${BUCKET:-thinkless-sadikh} PATH="$HOME/.local/bin:$PATH" TZ=Asia/Kolkata
source ~/venv/bin/activate
mkdir -p logs results outputs
M=Qwen/Qwen3.5-2B
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S IST')] $*" | tee -a logs/serve.log; }
for d in best best-awq; do [ -d "outputs/$d" ] || gcloud storage rsync -r "gs://$BUCKET/run/outputs/$d" "outputs/$d" --quiet; done
[ "${FP8_ONLY:-0}" = 1 ] || rm -f results/bench.jsonl   # FP8_ONLY appends to the earlier results
NGPU=$(nvidia-smi -L | wc -l)

MTP='--speculative-config {"method":"mtp","num_speculative_tokens":2}'
DRAFT='--speculative-config {"model":"Qwen/Qwen3.5-0.8B","num_speculative_tokens":4}'
CONFIGS=("base|$M|" "base-mtp|$M|$MTP" "thinkless|outputs/best|" "thinkless-awq|outputs/best-awq|"
         "thinkless-awq-mtp|outputs/best-awq|$MTP" "thinkless-awq-draft|outputs/best-awq|$DRAFT")
# FP8 run, added later (AWQ lost too much accuracy)
[ "${FP8_ONLY:-0}" = 1 ] && CONFIGS=("thinkless-fp8|outputs/best-fp8|" "thinkless-fp8-mtp|outputs/best-fp8|$MTP")

bench_one() {  # index label model extra-args
  local i=$1 label=$2 model=$3 extra=$4 gpu=$(( $1 % NGPU )) port=$(( 8000 + $1 ))
  CUDA_VISIBLE_DEVICES=$gpu vllm serve "$model" --dtype bfloat16 --served-model-name thinkless --port $port \
    --max-model-len 10240 $extra > "logs/serve_$label.log" 2>&1 &
  local pid=$!
  for _ in $(seq 180); do curl -sf localhost:$port/health >/dev/null && break; sleep 5; done
  python bench.py --label "$label" --tokenizer $M --url http://localhost:$port --concurrency 1 --num 10 --max-tokens 8192 \
    && python bench.py --label "$label" --tokenizer $M --url http://localhost:$port --concurrency 16 --num 64 --max-tokens 8192 \
    || echo "benchmark failed for $label (see logs/serve_$label.log)"
  kill $pid; wait $pid 2>/dev/null
}
log "serving benchmarks: ${#CONFIGS[@]} configurations in parallel on $NGPU GPUs"
for i in "${!CONFIGS[@]}"; do
  IFS='|' read -r label model extra <<< "${CONFIGS[$i]}"
  bench_one "$i" "$label" "$model" "$extra" >> logs/serve.log 2>&1 &
  [ $(( (i + 1) % NGPU )) = 0 ] && wait   # more configs than GPUs: run in waves
done
wait
while read -r l; do log "   $l"; done < results/bench.jsonl
python plot.py >> logs/serve.log 2>&1
gcloud storage rsync -r results "gs://$BUCKET/run/results" --quiet
gcloud storage rsync -r logs "gs://$BUCKET/run/logs" --quiet
log "SERVING BENCHMARKS COMPLETE"
[ "${NO_SHUTDOWN:-0}" = 1 ] || sudo shutdown -h +1
