#!/usr/bin/env bash
# CPU release VM (thinkless-release, us-central1-a, next to the bucket): Python env, models from the bucket, bf16
# conversion + check. Log: ~/release/setup.log
set -euo pipefail
mkdir -p ~/release && cd ~/release
exec > >(tee -a setup.log) 2>&1
echo "[$(TZ=Asia/Kolkata date '+%F %T IST')] setup start"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
[ -d venv ] || uv venv venv --python 3.11
source venv/bin/activate
uv pip install --index-url https://download.pytorch.org/whl/cpu torch
uv pip install "transformers==5.17.0" safetensors accelerate "huggingface_hub[hf_transfer]" jinja2
mkdir -p models
for d in best sft; do gcloud storage rsync -r "gs://thinkless-sadikh/run/outputs/$d" "models/$d-fp32" --quiet; done
python convert_bf16.py models/best-fp32 models/ThinkLess-2B
python convert_bf16.py models/sft-fp32 models/ThinkLess-2B-SFT
python check_bf16.py models/best-fp32 models/ThinkLess-2B
python check_bf16.py models/sft-fp32 models/ThinkLess-2B-SFT
du -sh models/*
echo "[$(TZ=Asia/Kolkata date '+%F %T IST')] setup done"
