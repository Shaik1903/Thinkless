"""Sanity check a converted bf16 folder on CPU: all weights bf16, and the fp32 and bf16 models agree on a greedy answer.

Usage: python check_bf16.py FP32_DIR BF16_DIR
"""
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

fp32_dir, bf16_dir = sys.argv[1], sys.argv[2]
tok = AutoTokenizer.from_pretrained(bf16_dir)
msgs = [{"role": "user", "content": "What is 17 * 24? Put your final answer within \\boxed{}."}]
ids = tok.apply_chat_template(msgs, add_generation_prompt=True, enable_thinking=False, return_tensors="pt",
                              return_dict=True)["input_ids"]  # Transformers 5 returns a BatchEncoding
outs = []
for d, dtype in ((bf16_dir, torch.bfloat16), (fp32_dir, torch.bfloat16)):  # fp32 cast at load = what the evals did
    m = AutoModelForCausalLM.from_pretrained(d, dtype=dtype)
    if d == bf16_dir:
        dts = {p.dtype for p in m.parameters()}
        assert dts == {torch.bfloat16}, dts
    with torch.no_grad():
        o = m.generate(ids, max_new_tokens=40, do_sample=False)
    outs.append(tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True))
    del m
print("bf16 folder :", repr(outs[0][:200]))
print("fp32 as bf16:", repr(outs[1][:200]))
assert outs[0] == outs[1], "converted weights differ from casting the fp32 checkpoint at load time"
print("CHECK OK: identical greedy output, all parameters bf16")
