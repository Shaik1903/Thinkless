"""Restore what Transformers/TRL drop from Qwen3.5 checkpoints, so vLLM can serve them.

1. MTP weights: Transformers ignores the mtp.* tensors when loading, so trained checkpoints are saved without
   them and vLLM's MTP speculative decoding has nothing to load. Our training does not change the heads, so we
   copy the base model's tensors byte-for-byte (dtype-agnostic, no torch needed).
2. Processor files: vLLM loads Qwen3.5 as a vision-language model and needs preprocessor_config.json etc.
   GRPO checkpoints (saved with only a tokenizer) lack them. We copy config files that are MISSING,
   never overwriting trained files and never copying the base weight index.
Usage: python restore_base.py BASE_DIR_OR_HF_ID CHECKPOINT_DIR
"""
import json
import re
import shutil
import struct
import sys
from pathlib import Path

MTP_KEY = re.compile(r"(^|\.)mtp\.")
CONFIG_GLOBS = ("*.json", "*.jinja")
NEVER_COPY = {"model.safetensors.index.json"}  # maps weights to the BASE shard files


def _header(path):
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return json.loads(f.read(n)), 8 + n


def _keys(ckpt: Path) -> dict:
    """tensor name -> file name, for every safetensors file in a checkpoint."""
    return {k: f.name for f in sorted(ckpt.glob("*.safetensors")) for k in _header(f)[0] if k != "__metadata__"}


def copy_mtp(base: Path, ckpt: Path) -> int:
    base, ckpt = Path(base), Path(ckpt)
    weight_map = _keys(ckpt)
    if any(MTP_KEY.search(k) for k in weight_map):
        return 0
    header, blob = {}, bytearray()
    for f in sorted(base.glob("*.safetensors")):
        meta, data_start = _header(f)
        raw = f.read_bytes()
        for k, info in meta.items():
            if k == "__metadata__" or not MTP_KEY.search(k):
                continue
            start, end = info["data_offsets"]
            header[k] = {"dtype": info["dtype"], "shape": info["shape"],
                         "data_offsets": [len(blob), len(blob) + end - start]}
            blob += raw[data_start + start:data_start + end]
    if not header:
        return 0
    head = json.dumps(header).encode()
    head += b" " * (-len(head) % 8)  # safetensors pads the header to 8-byte alignment
    (ckpt / "mtp.safetensors").write_bytes(struct.pack("<Q", len(head)) + head + blob)
    weight_map.update({k: "mtp.safetensors" for k in header})
    (ckpt / "model.safetensors.index.json").write_text(json.dumps({"metadata": {}, "weight_map": weight_map}, indent=2))
    return len(header)


def copy_missing_files(base: Path, ckpt: Path) -> list[str]:
    base, ckpt = Path(base), Path(ckpt)
    copied = []
    for pattern in CONFIG_GLOBS:
        for f in sorted(base.glob(pattern)):
            if f.name not in NEVER_COPY and not (ckpt / f.name).exists():
                shutil.copy(f, ckpt / f.name)
                copied.append(f.name)
    return copied


if __name__ == "__main__":
    src = Path(sys.argv[1])
    if not src.is_dir():  # a Hugging Face model id: use the cached snapshot
        from huggingface_hub import snapshot_download
        src = Path(snapshot_download(sys.argv[1], allow_patterns=["*.safetensors", *CONFIG_GLOBS]))
    dst = Path(sys.argv[2])
    files = copy_missing_files(src, dst)
    print(f"copied {copy_mtp(src, dst)} MTP tensors and {len(files)} missing files {files} into {dst}")
