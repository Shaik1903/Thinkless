"""Pick GRPO's completion cap from the SFT model's own evaluation (data-driven, decided at GRPO start).

If >= THRESHOLD of the SFT model's correct answers on MATH-500 + validation needed more than 8k tokens, an 8k cap would
score them 0 and fight what SFT just taught -> use 12k (and give vLLM less memory so training fits). Otherwise keep 8k.
"""
import json
from pathlib import Path

THRESHOLD = 0.25


def decide(records, threshold=THRESHOLD) -> dict:
    correct = [r["n_tokens"] for r in records if r["correct"] and r["bench"] in ("math500", "mathval")]
    over = sum(t > 8192 for t in correct) / len(correct) if correct else 0.0
    cap = 12288 if over >= threshold else 8192
    return {"correct_answers": len(correct), "share_over_8k": round(over, 4), "threshold": threshold, "max_len": cap}


def decide_from_files(path="results/sft.jsonl") -> dict:
    if not Path(path).exists():
        return {"max_len": 8192, "reason": f"{path} missing; default 8k"}
    out = decide(map(json.loads, open(path)))
    Path("results").mkdir(exist_ok=True)
    Path("results/grpo_budget.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    print(decide_from_files())
