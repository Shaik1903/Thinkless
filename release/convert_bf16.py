"""fp32 training checkpoint -> bf16 release folder (half the size, what every eval/serving run used via dtype=bf16).

Usage: python convert_bf16.py SRC DST
Casts every floating-point tensor in each *.safetensors file to bf16 (same file names), rewrites the index's
total_size, sets dtype in config.json, copies tokenizer/processor files, and drops training-only artifacts.
"""
import json
import shutil
import sys
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file

SKIP = {"trainer_state.json", "training_args.bin", "optimizer.pt", "scheduler.pt", "README.md"}
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.mkdir(parents=True, exist_ok=True)
total = 0
for f in sorted(src.glob("*.safetensors")):
    out = {}
    with safe_open(f, framework="pt") as sf:
        meta = sf.metadata()
        for k in sf.keys():
            t = sf.get_tensor(k)
            out[k] = t.to(torch.bfloat16) if t.is_floating_point() else t
    save_file(out, dst / f.name, metadata=meta)
    total += sum(t.numel() * t.element_size() for t in out.values())
    print(f"{f.name}: {len(out)} tensors -> bf16")
for f in src.iterdir():
    if f.is_file() and f.suffix != ".safetensors" and f.name not in SKIP and not f.name.startswith("rng_state"):
        shutil.copy2(f, dst / f.name)
idx = dst / "model.safetensors.index.json"
if idx.exists():
    d = json.loads(idx.read_text())
    d.setdefault("metadata", {})["total_size"] = total
    idx.write_text(json.dumps(d, indent=2))


def set_dtype(c):
    for k in ("dtype", "torch_dtype"):
        if k in c:
            c[k] = "bfloat16"
    for v in c.values():
        if isinstance(v, dict):
            set_dtype(v)


cfg = json.loads((dst / "config.json").read_text())
cfg["dtype"] = "bfloat16"
set_dtype(cfg)
(dst / "config.json").write_text(json.dumps(cfg, indent=2))
print(f"done: {dst} ({total / 1e9:.2f} GB of tensors)")
