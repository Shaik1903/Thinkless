"""Pick the GRPO checkpoint: fewest tokens among those not worse than SFT on the validation set.

Compares each checkpoint to SFT on the same validation problems (paired), with SFT's 32k run scored at an
8k budget to match the checkpoint runs, which are capped at 8k.
"""
import json
from pathlib import Path
from statistics import mean

from metrics import paired_diff

TOLERANCE = -0.015  # checkpoint may be at most 1.5 points below SFT


def load(path, bench="mathval"):
    return [r for r in map(json.loads, open(path)) if r["bench"] == bench]


ref = load("results/sft.jsonl")
rows = []
paths = [p for p in Path("results").glob("val_checkpoint-*.jsonl") if ".shard" not in p.name]
for p in sorted(paths, key=lambda p: int(p.stem.split("-")[1])):
    recs = load(p)
    d = paired_diff(ref, recs, budget=8192)
    rows.append((p.stem.removeprefix("val_"), mean(r["n_tokens"] for r in recs), d))
    lo, hi = d["ci95"]
    print(f"{rows[-1][0]:18s} tokens={rows[-1][1]:6.0f} acc_vs_sft={d['diff'] * 100:+.1f} "
          f"[{lo * 100:+.1f}, {hi * 100:+.1f}] on {d['n_problems']} problems")

ok = [r for r in rows if r[2]["diff"] >= TOLERANCE]
print("selected:", min(ok, key=lambda r: r[1])[0] if ok else "none within tolerance - ship outputs/sft")
