"""Quality gates that stop the run. Exit code 1 + reasons printed when a gate fails.

baseline: our base-model scores vs the Qwen3.5-2B model card. Off by more than 5 points AND the published score
          outside our 95% CI means the eval harness is wrong (small sets like HMMT are noisy, hence the CI test).
sft:      SFT must not drop MATH-500 accuracy by more than 3 points vs the base model (thinking on).
grpo:     the shipped model must not drop GPQA by more than 3 points vs SFT (checkpoint selection only checks maths;
          HMMT is reported, not gated: 30 problems give a CI of about +/-12 points).
Usage: python check_gates.py baseline results/base_think.metrics.json
       python check_gates.py sft results/base_think.metrics.json results/sft.metrics.json
       python check_gates.py grpo results/sft.metrics.json results/grpo.metrics.json
"""
import json
import sys

PUBLISHED = {"gpqa": 0.516, "hmmt25": 0.229}  # Qwen3.5-2B model card, thinking mode


def baseline_problems(metrics: dict, tol: float = 0.05) -> list[str]:
    out = []
    for bench, pub in PUBLISHED.items():
        acc = metrics[bench]["accuracy"]
        lo, hi = metrics[bench]["accuracy_ci95"]
        if abs(acc - pub) > tol and not lo <= pub <= hi:
            out.append(f"{bench}: ours {acc:.3f} [{lo:.3f}-{hi:.3f}] vs published {pub:.3f}")
    return out


def sft_problems(base: dict, sft: dict, bench: str = "math500", max_drop: float = 0.03,
                 names: tuple[str, str] = ("SFT", "base")) -> list[str]:
    drop = base[bench]["accuracy"] - sft[bench]["accuracy"]
    return [f"{bench}: {names[0]} {sft[bench]['accuracy']:.3f} vs {names[1]} {base[bench]['accuracy']:.3f} "
            f"(drop {drop * 100:.1f} points > {max_drop * 100:.0f})"] if drop > max_drop else []


if __name__ == "__main__":
    load = lambda p: json.load(open(p))
    if sys.argv[1] == "baseline":
        problems = baseline_problems(load(sys.argv[2]))
    elif sys.argv[1] == "grpo":
        problems = sft_problems(load(sys.argv[2]), load(sys.argv[3]), bench="gpqa", names=("GRPO", "SFT"))
    else:
        problems = sft_problems(load(sys.argv[2]), load(sys.argv[3]))
    print("GATE PASSED" if not problems else "GATE FAILED:\n  " + "\n  ".join(problems))
    sys.exit(1 if problems else 0)
