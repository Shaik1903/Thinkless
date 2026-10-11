"""Turns per-sample generation records into the numbers we report."""
import json
import random
import sys
from collections import defaultdict
from statistics import mean, median

BUDGETS = (2048, 4096, 8192, 16384, 32768, 65536, 81920)


def bootstrap_ci(records, n_boot=1000, seed=0) -> list[float]:
    """95% CI for accuracy. Resamples PROBLEMS (not samples), since samples of one problem are correlated."""
    per_problem = defaultdict(list)
    for r in records:
        per_problem[r["qid"]].append(float(r["correct"]))
    scores = [mean(v) for v in per_problem.values()]
    rng = random.Random(seed)
    boots = sorted(mean(rng.choices(scores, k=len(scores))) for _ in range(n_boot))
    return [boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]]


def _per_problem(records, budget):
    """qid -> mean correctness, counting a sample only if it was right within `budget` tokens."""
    by_q = defaultdict(list)
    for r in records:
        by_q[r["qid"]].append(float(r["correct"] and (budget is None or r["n_tokens"] <= budget)))
    return {q: mean(v) for q, v in by_q.items()}


def paired_diff(ref, new, budget=None, n_boot=1000, seed=0) -> dict:
    """Accuracy of `new` minus `ref` on the SAME problems, with a bootstrap CI over problems.

    Pairing removes problem difficulty from the noise, so small checkpoint-vs-SFT gaps become measurable.
    `budget` applies to `ref` (e.g. SFT's 32k run scored at 8k to match checkpoint runs capped at 8k).
    """
    a, b = _per_problem(ref, budget), _per_problem(new, None)
    # sorted: set order follows per-process string hashing, which made the "seeded" CI differ between runs
    diffs = [b[q] - a[q] for q in sorted(a.keys() & b.keys())]
    rng = random.Random(seed)
    boots = sorted(mean(rng.choices(diffs, k=len(diffs))) for _ in range(n_boot))
    return {"diff": mean(diffs), "ci95": [boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]],
            "n_problems": len(diffs)}


def summarize(records, budgets=BUDGETS) -> dict:
    by_bench = defaultdict(list)
    for r in records:
        by_bench[r["bench"]].append(r)
    out = {}
    for bench, rs in by_bench.items():
        tokens = [r["n_tokens"] for r in rs]
        out[bench] = {
            "n": len(rs),
            "accuracy": mean(r["correct"] for r in rs),
            "accuracy_ci95": bootstrap_ci(rs),
            "mean_tokens": mean(tokens),
            "median_tokens": median(tokens),
            "truncation_rate": mean(not r["finished"] for r in rs),
            # correct at budget B = finished with the right answer within B tokens
            "budget_accuracy": {str(b): mean(r["correct"] and r["n_tokens"] <= b for r in rs) for b in budgets},
        }
    return out


def collapsed(rewards, ratio=0.7) -> bool:
    """GRPO reward collapse: the last 2 steps average below `ratio` x the best 5-step average so far."""
    if len(rewards) < 7:
        return False
    best = max(mean(rewards[i:i + 5]) for i in range(len(rewards) - 4))
    return mean(rewards[-2:]) < ratio * best


if __name__ == "__main__":
    path = sys.argv[1]
    res = summarize(json.loads(line) for line in open(path))
    json.dump(res, open(path.replace(".jsonl", ".metrics.json"), "w"), indent=2)
    for bench, m in res.items():
        lo, hi = m["accuracy_ci95"]
        print(f"{bench:8s} n={m['n']:5d} acc={m['accuracy']:.3f} [{lo:.3f}-{hi:.3f}] "
              f"tokens={m['mean_tokens']:7.0f} trunc={m['truncation_rate']:.3f} "
              f"acc@4k={m['budget_accuracy']['4096']:.3f}")
