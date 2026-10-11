#!/usr/bin/env bash
# Installs the training/eval env (~/venv) and a separate quantization env (~/venv-quant).
set -euo pipefail
# g++: vLLM's sampler (flashinfer) JIT-compiles kernels on first use; the GCP image lacks a C++ compiler
command -v g++ >/dev/null || { sudo apt-get update -q && sudo apt-get install -y -q g++; }
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh  # the GCP image ships without pip
export PATH="$HOME/.local/bin:$PATH"
uv venv --clear ~/venv --python 3.11
source ~/venv/bin/activate
uv pip install -r requirements.txt
# causal-conv1d has no wheel for this torch/CUDA; use a prebuilt one from the bucket if there is one
if [ -n "${BUCKET:-}" ] && gcloud storage ls "gs://$BUCKET/wheels/causal_conv1d-*.whl" >/dev/null 2>&1; then
  mkdir -p ~/wheels && gcloud storage cp "gs://$BUCKET/wheels/causal_conv1d-*.whl" ~/wheels/
  uv pip install ~/wheels/causal_conv1d-*.whl
else
  echo "causal-conv1d not installed, training will use the slower kernels"
fi
uv venv --clear ~/venv-quant --python 3.11
VIRTUAL_ENV=~/venv-quant uv pip install llmcompressor datasets math-verify
python -c "import vllm, trl, transformers, torch; print('vllm', vllm.__version__, 'trl', trl.__version__, 'transformers', transformers.__version__, 'torch', torch.__version__, 'cuda', torch.version.cuda)"
