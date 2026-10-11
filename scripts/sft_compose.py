"""Build the final SFT set from all generation passes, balance it, and report its composition.

Inputs: data/sft_samples.jsonl (2B, 8k), data/sft_retry.jsonl (2B, 16k), data/sft_teacher.jsonl (Qwen3.5-9B, 16k).
Per problem keeps the shortest correct+finished answer across all passes. The teacher is only asked about problems the
2B never solved, so every kept teacher answer is a fill-in. GSM8K is then capped at the number of MATH examples so the
set isn't dominated by easy problems.
Modes:  python scripts/sft_compose.py unsolved   -> data/sft_teacher_qids.txt (problems the 2B never solved)
        python scripts/sft_compose.py build      -> data/sft.jsonl + composition report
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

from build_sft_data import select_shortest_correct
from data import load_sft_problems

PASSES = {"self-8k": "data/sft_samples.jsonl", "self-16k": "data/sft_retry.jsonl", "teacher-9B": "data/sft_teacher.jsonl"}


def load_all():
    recs = []
    for tag, path in PASSES.items():
        if Path(path).exists():
            recs += [dict(json.loads(line), source=tag) for line in open(path)]
    return recs


def subject(qid):
    return "gsm8k" if qid.startswith("gsm8k") else "math-" + qid.split("-")[2]


def main(mode):
    problems = load_sft_problems()
    best = select_shortest_correct(load_all())
    if mode == "unsolved":
        missing = [p.qid for p in problems if p.qid not in best]
        Path("data/sft_teacher_qids.txt").write_text("\n".join(missing))
        print(f"2B solved {len(best)}/{len(problems)}; asking the teacher about {len(missing)} problems")
        return
    gsm = [q for q in best if subject(q) == "gsm8k"]
    math = [q for q in best if subject(q) != "gsm8k"]
    random.Random(0).shuffle(gsm)  # random tie-break among equal lengths
    # cap GSM8K at the MATH count, keeping the SHORTEST: a 10k-token answer to a grade-school problem teaches the
    # over-thinking we're removing (hard MATH problems are not capped; they legitimately need longer solutions)
    gsm.sort(key=lambda q: best[q]["n_tokens"])
    dropped = set(gsm[len(math):])
    keep = [q for q in best if q not in dropped]
    # always train on the 2B's own prompt text (the teacher's chat template could differ slightly)
    student_prompt = {r["qid"]: r["prompt"] for r in map(json.loads, open(PASSES["self-8k"]))}
    with open("data/sft.jsonl", "w") as f:
        for q in keep:
            f.write(json.dumps({"prompt": student_prompt[q], "completion": best[q]["completion"]}) + "\n")
    total = Counter(subject(p.qid) for p in problems)
    kept = Counter(subject(q) for q in keep)
    src = Counter((subject(q), best[q]["source"]) for q in keep)
    toks = {}
    for q in keep:
        toks.setdefault(subject(q), []).append(best[q]["n_tokens"])
    print(f"FINAL SFT SET: {len(keep)} examples (solved {len(best)}/{len(problems)}; GSM8K capped: dropped {len(dropped)})")
    for s in sorted(total):
        mean = sum(toks.get(s, [0])) / max(len(toks.get(s, [])), 1)
        print(f"  {s:32s} {kept[s]:5d} ({kept[s] / len(keep):5.1%} of set) mean {mean:6.0f} tok | "
              f"self-8k {src[(s, 'self-8k')]:4d} self-16k {src[(s, 'self-16k')]:4d} teacher {src[(s, 'teacher-9B')]:4d}")
    # publishable dataset: one rich row per example (question, gold, trace, length, which model wrote it)
    by_qid = {p.qid: p for p in problems}
    Path("results/datasets").mkdir(parents=True, exist_ok=True)
    with open("results/datasets/thinkless_sft.jsonl", "w") as f:
        for q in keep:
            p, r = by_qid[q], best[q]
            f.write(json.dumps({"id": q, "source_dataset": "gsm8k" if q.startswith("gsm8k") else "hendrycks_math",
                                "subject": subject(q), "question": p.question, "gold_answer": p.answer,
                                "completion": r["completion"], "n_tokens": r["n_tokens"],
                                "generator": {"self-8k": "Qwen3.5-2B (8k budget)", "self-16k": "Qwen3.5-2B (16k retry)",
                                              "teacher-9B": "Qwen3.5-9B (teacher fill-in)"}[r["source"]]}) + "\n")
    Path("results/sft_composition.json").write_text(json.dumps(
        {"examples": len(keep), "per_subject": dict(kept), "per_source": {f"{a}|{b}": n for (a, b), n in src.items()}},
        indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
