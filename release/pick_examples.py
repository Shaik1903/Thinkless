"""Example candidates for the model card, per benchmark: ThinkLess correct, short and readable vs base.

Two kinds: (A) both correct, largest token saving; (B) base fails (wrong or cut off at 82k) while ThinkLess solves it.
Writes release/example_candidates.md (question, gold, base outcome/tokens, full ThinkLess output).
"""
import gzip
import json
from collections import defaultdict
from pathlib import Path

D = Path(__file__).parent / "eval_outputs"


def load(name):
    by = defaultdict(list)
    with gzip.open(D / f"eval_outputs_{name}.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            by[(r["bench"], r["qid"])].append(r)
    return by


def repetitive(text):  # share of repeated lines: readable answers have few
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return 1 - len(set(lines)) / max(1, len(lines))


base, tl = load("base_think"), load("grpo")
MAX_TL = {"gsm8k": 1200, "math500": 2500, "gpqa": 3500}
out = ["# Example candidates (ThinkLess vs base, 82k budget)\n"]
for bench in ("gsm8k", "math500", "gpqa"):
    rows = []
    for key, trs in tl.items():
        if key[0] != bench or key not in base:
            continue
        good = [r for r in trs if r["correct"] and r["finished"] and r["n_tokens"] <= MAX_TL[bench]
                and repetitive(r["completion"]) < 0.08]
        if not good:
            continue
        t = min(good, key=lambda r: r["n_tokens"])
        brs = base[key]
        b_ok = [r for r in brs if r["correct"]]
        kind = "A" if b_ok else "B"
        b = max(b_ok, key=lambda r: r["n_tokens"]) if b_ok else max(brs, key=lambda r: r["n_tokens"])
        rows.append((kind, b["n_tokens"] / t["n_tokens"], t, b))
    for kind in ("A", "B"):
        top = sorted((r for r in rows if r[0] == kind), key=lambda r: -r[1])[:3]
        out.append(f"\n## {bench.upper()}: type {kind} ({'both correct' if kind == 'A' else 'base fails, ThinkLess solves'})\n")
        for i, (_, ratio, t, b) in enumerate(top, 1):
            bo = "correct" if b["correct"] else ("cut off at 82k" if not b["finished"] else "wrong")
            q = t["prompt"].split("<|im_start|>user\n")[-1].split("<|im_end|>")[0].strip()
            out.append(f"### {bench}-{kind}{i} ({t['qid']}): base {b['n_tokens']:,} tokens ({bo}) -> "
                       f"ThinkLess {t['n_tokens']:,} tokens ({ratio:.1f}x fewer)\n\n**Question:** {q}\n\n"
                       f"**ThinkLess output:**\n\n```text\n{t['completion'].strip()}\n```\n")
(Path(__file__).parent / "example_candidates.md").write_text("\n".join(out), encoding="utf-8")
for line in out:
    if line.startswith("### ") or line.startswith("\n## "):
        print(line.strip())
