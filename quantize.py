"""AWQ W4A16 (default) or FP8-dynamic fallback, via llm-compressor. Run with ~/venv-quant/bin/python."""
import os
import sys

from datasets import load_dataset
from llmcompressor import oneshot
from llmcompressor.modifiers.awq import AWQModifier
from llmcompressor.modifiers.quantization import QuantizationModifier
from transformers import AutoModelForCausalLM, AutoTokenizer

src, dst = sys.argv[1], sys.argv[2]
method = sys.argv[3] if len(sys.argv) > 3 else "awq"
IGNORE = ["lm_head", "re:.*visual.*", "re:.*mtp.*"]  # keep output head, vision tower and MTP heads in 16-bit

tok = AutoTokenizer.from_pretrained(src)
model = AutoModelForCausalLM.from_pretrained(src, dtype="bfloat16")  # checkpoints are saved fp32; serve bf16

if method == "awq":
    calib = load_dataset("json", data_files=os.environ.get("CALIB", "data/sft.jsonl"), split="train")
    n = min(256, len(calib))  # 256 in the real run; fewer in the tooling gate
    calib = calib.shuffle(seed=0).select(range(n))
    calib = calib.map(lambda r: tok(r["prompt"] + r["completion"], truncation=True, max_length=2048),
                      remove_columns=calib.column_names)
    # processor=tok: otherwise llm-compressor loads Qwen3.5's multimodal processor, which needs torchvision
    oneshot(model=model, processor=tok, dataset=calib, max_seq_length=2048, num_calibration_samples=n,
            recipe=[AWQModifier(targets=["Linear"], scheme="W4A16_ASYM", ignore=IGNORE)])
else:
    oneshot(model=model, recipe=[QuantizationModifier(targets="Linear", scheme="FP8_DYNAMIC", ignore=IGNORE)])

model.save_pretrained(dst, save_compressed=True)
tok.save_pretrained(dst)
