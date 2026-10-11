#!/usr/bin/env bash
# Full run on an 8x H100 VM: baselines -> SFT data -> SFT -> GRPO -> eval -> quantize -> serving bench.
# Resumable: done stages are skipped on rerun. A failed gate or a stage failing twice halts and shuts the VM down.
set -uo pipefail
cd ~/thinkless
set -a; . ./.env; set +a
export BUCKET=${BUCKET:-thinkless-sadikh} PATH="$HOME/.local/bin:$PATH" WANDB_PROJECT=thinkless TZ=Asia/Kolkata
source ~/venv/bin/activate
mkdir -p logs state results data outputs
M=Qwen/Qwen3.5-2B
EVAL_SETS="gsm8k math500 hmmt25 gpqa"
GRPO_HOURS=${GRPO_HOURS:-6}

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S IST')] $*" | tee -a logs/pipeline.log; }
sync_small() {
  gcloud storage rsync -r results "gs://$BUCKET/run/results" --quiet >/dev/null 2>&1
  gcloud storage rsync -r logs "gs://$BUCKET/run/logs" --quiet >/dev/null 2>&1
  gcloud storage rsync -r state "gs://$BUCKET/run/state" --quiet >/dev/null 2>&1
}
halt() {  # touch state/keep_alive_on_halt to keep the VM up after a halt
  log "HALT: $*"; echo "$*" > state/HALTED; sync_small
  [ -f state/keep_alive_on_halt ] || sudo shutdown -h +1
  exit 1
}

stage() {  # stage NAME FUNCTION: skip if done, one retry, then halt
  local name=$1 fn=$2
  [ -f "state/$name.done" ] && { log "skip  $name (already done)"; return 0; }
  for attempt in 1 2; do
    log "START $name (attempt $attempt)"
    if "$fn" "$attempt" >> "logs/$name.log" 2>&1; then
      touch "state/$name.done"; log "DONE  $name"; sync_small; return 0
    fi
    log "FAIL  $name (attempt $attempt); last lines: $(tail -3 "logs/$name.log" | tr '\n' ' ' | cut -c1-400)"
  done
  halt "stage $name failed twice (see logs/$name.log)"
}
metrics_line() { grep -E "^(gsm8k|math500|hmmt25|gpqa|mathval|sft) " "logs/$1.log" | tail -6 | while read -r l; do log "   $l"; done; }

# --- baselines and SFT ---
s_overlap()       { python check_overlap.py; }
s_base_think()    { bash scripts/sharded.sh results/base_think --model $M --sets $EVAL_SETS; }
s_base_nothink()  { bash scripts/sharded.sh results/base_nothink --model $M --sets $EVAL_SETS --no-thinking; }
s_sft_data()      { bash scripts/sharded.sh data/sft_samples --model $M --sets sft --n 4 --max-tokens 8192 \
                      && python build_sft_data.py data/sft_samples.jsonl data/sft.jsonl; }
s_sft_retry() {  # unsolved at 8k -> 4 more samples at 16k
  PYTHONPATH=. python scripts/sft_retry.py data/sft_samples.jsonl || return 1
  if [ -s data/sft_retry_qids.txt ]; then
    bash scripts/sharded.sh data/sft_retry --model $M --sets sft_retry --n 4 --max-tokens 16384 || return 1
  else
    : > data/sft_retry.jsonl
  fi
  cat data/sft_samples.jsonl data/sft_retry.jsonl > data/sft_all.jsonl
  python build_sft_data.py data/sft_all.jsonl data/sft.jsonl
}
s_sft_teacher() {  # still unsolved -> 2 samples from Qwen3.5-9B
  PYTHONPATH=. python scripts/sft_compose.py unsolved || return 1
  [ -s data/sft_teacher_qids.txt ] || return 0
  bash scripts/sharded.sh data/sft_teacher --model Qwen/Qwen3.5-9B --sets sft_teacher --n 2 --max-tokens 16384
}
s_sft_compose() { PYTHONPATH=. python scripts/sft_compose.py build; }
s_sft_train() {
  accelerate launch --multi_gpu --num_processes 8 train_sft.py $M data/sft.jsonl outputs/sft || return 1
  ck=$(ls -d outputs/sft/checkpoint-* 2>/dev/null | sort -t- -k2 -n | tail -1)
  [ -n "$ck" ] && cp "$ck/trainer_state.json" results/sft_trainer_state.json
  python restore_base.py $M outputs/sft && rm -rf outputs/sft/checkpoint-*
}
s_sft_eval()      { bash scripts/sharded.sh results/sft --model outputs/sft --sets $EVAL_SETS mathval; }

# --- GRPO ---
s_grpo() {
  local mem=0.35; [ "$1" = 2 ] && grep -q "out of memory" logs/grpo.log && mem=0.25   # retry with less vLLM memory after an OOM
  (while sleep 1200; do gcloud storage rsync -r outputs/grpo "gs://$BUCKET/run/outputs/grpo" --quiet >/dev/null 2>&1; done) &
  local syncer=$!
  local t0=$SECONDS
  VLLM_GPU_MEM=$mem MAX_HOURS=$GRPO_HOURS accelerate launch --multi_gpu --num_processes 8 train_grpo.py outputs/sft outputs/grpo
  local rc=$?
  if [ $rc = 0 ] && [ -f outputs/grpo/SPARSE_REWARD ] && [ ! -f state/grpo_mixed ]; then
    log "GRPO safeguard fired: $(cat outputs/grpo/SPARSE_REWARD). Restarting once with MATH L3-5 mixed in."
    touch state/grpo_mixed
    mv outputs/grpo outputs/grpo_sparse_attempt
    local left; left=$(python -c "print(max(1.0, $GRPO_HOURS - ($SECONDS - $t0) / 3600))")
    GRPO_MIX_MATH=1 VLLM_GPU_MEM=$mem MAX_HOURS=$left accelerate launch --multi_gpu --num_processes 8 \
      train_grpo.py outputs/sft outputs/grpo
    rc=$?
  fi
  kill $syncer 2>/dev/null
  ck=$(ls -d outputs/grpo/checkpoint-* 2>/dev/null | sort -t- -k2 -n | tail -1)
  [ -n "$ck" ] && cp "$ck/trainer_state.json" results/grpo_trainer_state.json
  return $rc
}

# --- selection, eval, quantization, serving ---
s_select() {
  # every 2nd checkpoint plus the last one
  for ck in $(ls -d outputs/grpo/checkpoint-* | sort -t- -k2 -n | awk '{a[NR]=$0} END{for(i=1;i<=NR;i++) if(i%2==0||i==NR) print a[i]}'); do
    [ -f "results/val_$(basename "$ck").metrics.json" ] && continue
    python restore_base.py $M "$ck" && \
      bash scripts/sharded.sh "results/val_$(basename "$ck")" --model "$ck" --sets mathval --max-tokens 8192 || return 1
  done
  python select_checkpoint.py | tee results/selection.txt
  best=$(grep -oE "^selected: checkpoint-[0-9]+" results/selection.txt | cut -d' ' -f2)
  rm -rf outputs/best
  if [ -n "$best" ]; then cp -r "outputs/grpo/$best" outputs/best; else cp -r outputs/sft outputs/best; fi
  python restore_base.py $M outputs/best
}
s_final_eval()    { bash scripts/sharded.sh results/grpo --model outputs/best --sets $EVAL_SETS; }
s_awq() {
  CALIB=data/sft.jsonl ~/venv-quant/bin/python quantize.py outputs/best outputs/best-awq awq || \
    CALIB=data/sft.jsonl ~/venv-quant/bin/python quantize.py outputs/best outputs/best-awq fp8 || return 1
  python restore_base.py $M outputs/best-awq
}
s_awq_eval()      { bash scripts/sharded.sh results/grpo_awq --model outputs/best-awq --sets $EVAL_SETS; }
s_export() {
  python export_examples.py && python plot.py || return 1
  # compressed rollouts and eval outputs for the HF dataset
  mkdir -p results/datasets
  for f in data/sft_samples data/sft_retry data/sft_teacher; do
    [ -f "$f.jsonl" ] && gzip -c "$f.jsonl" > "results/datasets/rollouts_$(basename "$f").jsonl.gz"
  done
  for f in base_think base_nothink base_think_32k base_nothink_32k sft grpo grpo_awq; do
    [ -f "results/$f.jsonl" ] && gzip -c "results/$f.jsonl" > "results/datasets/eval_outputs_$f.jsonl.gz"
  done
  for d in best best-awq sft; do gcloud storage rsync -r "outputs/$d" "gs://$BUCKET/run/outputs/$d" --quiet; done
}

s_serve()         { NO_SHUTDOWN=1 bash scripts/serve_bench.sh; }
s_budget_force_gpqa() {
  for pair in "base:$M" "sft:outputs/sft" "thinkless:outputs/best"; do
    local name=${pair%%:*} path=${pair#*:}
    [ -f "results/bforce_gpqa_$name.metrics.json" ] && continue
    bash scripts/sharded.sh "results/bforce_gpqa_$name" --model "$path" --sets gpqa \
      --budget-force 2048 4096 8192 16384 --max-tokens 16384 || return 1
  done
}
s_fp8()           { ~/venv-quant/bin/python quantize.py outputs/best outputs/best-fp8 fp8 && python restore_base.py $M outputs/best-fp8; }
s_fp8_eval()      { bash scripts/sharded.sh results/grpo_fp8 --model outputs/best-fp8 --sets $EVAL_SETS; }
s_serve_fp8()     { NO_SHUTDOWN=1 FP8_ONLY=1 bash scripts/serve_bench.sh; }
s_budget_force() {  # cut thinking at 2k/4k/8k/16k and force an answer
  for pair in "base:$M" "sft:outputs/sft" "thinkless:outputs/best"; do
    local name=${pair%%:*} path=${pair#*:}
    [ -f "results/bforce_$name.metrics.json" ] && continue
    bash scripts/sharded.sh "results/bforce_$name" --model "$path" --sets gsm8k math500 \
      --budget-force 2048 4096 8192 16384 --max-tokens 16384 || return 1
  done
  python plot.py && gcloud storage rsync -r results "gs://$BUCKET/run/results" --quiet
}

log "pipeline start"
stage overlap s_overlap
stage base_think s_base_think;       metrics_line base_think
stage base_nothink s_base_nothink;   metrics_line base_nothink
if [ -f state/baseline_gate.override ]; then   # manual override, reason in the file
  log "gate baseline: overridden: $(cat state/baseline_gate.override)"
else
  python check_gates.py baseline results/base_think.metrics.json > logs/gate_baseline.log 2>&1 \
    || halt "baseline gate: $(tr '\n' ' ' < logs/gate_baseline.log)"
  log "gate baseline: $(head -1 logs/gate_baseline.log)"
fi
stage sft_data s_sft_data
stage sft_retry s_sft_retry
grep -E "kept|mean tokens|retrying" logs/sft_retry.log 2>/dev/null | while read -r l; do log "   $l"; done
stage sft_teacher s_sft_teacher
grep -E "asking the teacher|^sft_teacher " logs/sft_teacher.log 2>/dev/null | while read -r l; do log "   $l"; done
stage sft_compose s_sft_compose
grep -E "FINAL SFT SET|of set" logs/sft_compose.log 2>/dev/null | while read -r l; do log "   $l"; done
stage sft_train s_sft_train
stage sft_eval s_sft_eval;           metrics_line sft_eval
python check_gates.py sft results/base_think.metrics.json results/sft.metrics.json > logs/gate_sft.log 2>&1 \
  || halt "SFT gate: $(tr '\n' ' ' < logs/gate_sft.log)"
log "gate SFT: $(head -1 logs/gate_sft.log)"
stage grpo s_grpo
stage select s_select
stage final_eval s_final_eval;       metrics_line final_eval
# GPQA gate only warns: checkpoint selection looks at math only
python check_gates.py grpo results/sft.metrics.json results/grpo.metrics.json > logs/gate_grpo.log 2>&1 \
  || log "warning: GRPO gate: $(tr '\n' ' ' < logs/gate_grpo.log)"
log "gate GRPO (GPQA vs SFT): $(head -1 logs/gate_grpo.log)"
stage awq s_awq
stage awq_eval s_awq_eval;           metrics_line awq_eval
stage export s_export
stage serve s_serve
stage budget_force s_budget_force
stage budget_force_gpqa s_budget_force_gpqa
# FP8: added after AWQ lost 7-15 points
stage fp8 s_fp8
stage fp8_eval s_fp8_eval;           metrics_line fp8_eval
stage serve_fp8 s_serve_fp8
log "pipeline complete"
touch state/COMPLETE
sync_small
sudo shutdown -h +1
