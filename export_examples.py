"""Human-readable outputs: a CSV comparing every model's answer per question, and a showcase of the best examples.

results/examples.csv  one row per (benchmark, question): gold answer, and for each model: correct, tokens,
                      finished, final answer, and the start/end of its reasoning (full text is in the JSONL files)
results/showcase.md   the k questions where base AND ThinkLess are correct and ThinkLess saved the most tokens
Usage: python export_examples.py   (run from the repo root after the final evals)
"""
import csv
import json
from pathlib import Path

from data import load_eval
from grading import answer_part

MODELS = {"base": "results/base_think.jsonl", "sft": "results/sft.jsonl",
          "thinkless": "results/grpo.jsonl", "thinkless_awq": "results/grpo_awq.jsonl"}
BENCHES = ("gsm8k", "math500", "hmmt25", "gpqa")


def first_sample(records):
    """qid -> the sample-0 record (every model has at least one sample per question)."""
    return {r["qid"]: r for r in records if r["sample"] == 0}


def pick_showcase(base_recs, new_recs, k=6):
    base, new = first_sample(base_recs), first_sample(new_recs)
    both = [q for q in base.keys() & new.keys() if base[q]["correct"] and new[q]["correct"]]
    both.sort(key=lambda q: base[q]["n_tokens"] / max(new[q]["n_tokens"], 1), reverse=True)
    return [{"qid": q, "bench": base[q]["bench"], "base_tokens": base[q]["n_tokens"], "new_tokens": new[q]["n_tokens"],
             "base_completion": base[q]["completion"], "new_completion": new[q]["completion"]} for q in both[:k]]


def _load(path):
    return [json.loads(line) for line in open(path)] if Path(path).exists() else []


def main():
    problems = {p.qid: p for b in BENCHES for p in load_eval(b)}
    runs = {name: first_sample(_load(path)) for name, path in MODELS.items()}
    qids = sorted({q for recs in runs.values() for q in recs if q in problems})
    with open("results/examples.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        header = ["bench", "qid", "question", "gold"]
        for name in runs:
            header += [f"{name}_correct", f"{name}_tokens", f"{name}_finished", f"{name}_final_answer",
                       f"{name}_reasoning_start", f"{name}_reasoning_end"]
        w.writerow(header)
        for q in qids:
            p = problems[q]
            row = [q.split("-")[0], q, p.question, p.answer]
            for name, recs in runs.items():
                r = recs.get(q)
                if r is None:
                    row += [""] * 6
                    continue
                c = r["completion"]
                row += [r["correct"], r["n_tokens"], r["finished"], (answer_part(c, True) or "")[-400:].strip(),
                        c[:1500], c[-800:]]
            w.writerow(row)
    print(f"examples.csv: {len(qids)} questions x {len(runs)} models")

    picked = pick_showcase(_load(MODELS["base"]), _load(MODELS["thinkless"]), k=6)
    with open("results/showcase.md", "w", encoding="utf-8") as f:
        f.write("# ThinkLess vs base: correct answers with the largest token savings\n\n")
        for i, s in enumerate(picked, 1):
            p = problems[s["qid"]]
            f.write(f"## Example {i} ({s['bench']}): {s['base_tokens']:,} -> {s['new_tokens']:,} tokens "
                    f"({s['base_tokens'] / max(s['new_tokens'], 1):.1f}x fewer)\n\n")
            f.write(f"**Question:** {p.question}\n\n**Gold answer:** `{p.answer}`\n\n")
            f.write(f"**ThinkLess (full output, {s['new_tokens']:,} tokens):**\n\n```text\n{s['new_completion']}\n```\n\n")
            b = s["base_completion"]
            f.write(f"**Base model ({s['base_tokens']:,} tokens), start and end:**\n\n```text\n{b[:1200]}\n\n"
                    f"[... {s['base_tokens']:,} tokens total ...]\n\n{b[-800:]}\n```\n\n")
    print(f"showcase.md: {len(picked)} examples")


if __name__ == "__main__":
    main()
