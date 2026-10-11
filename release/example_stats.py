"""Base-vs-ThinkLess comparison material for model-card examples.

For each chosen example: token counts, outcome, where base first reached the final answer, how often it wrote
"Wait", and full outputs saved as text files (release/ThinkLess-2B/examples/). Prints a summary per example.
"""
import gzip
import json
import re
from pathlib import Path

D = Path(__file__).parent / "eval_outputs"
OUT = Path(__file__).parent / "ThinkLess-2B" / "examples"
OUT.mkdir(parents=True, exist_ok=True)
PICKS = {"gsm8k-A1": ("gsm8k", "gsm8k-test-684", "11"), "math500-A1": ("math500", "math500-5", "42"),
         "math500-B1": ("math500", "math500-97", "east"), "gsm8k-B1": ("gsm8k", "gsm8k-test-941", "842")}


def load(name, keys):
    out = {}
    with gzip.open(D / f"eval_outputs_{name}.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            k = (r["bench"], r["qid"])
            if k in keys:
                out.setdefault(k, []).append(r)
    return out


keys = {(b, q) for b, q, _ in PICKS.values()}
base, tl = load("base_think", keys), load("grpo", keys)
stats = {}
for tag, (b, q, ans) in PICKS.items():
    t = min((r for r in tl[(b, q)] if r["correct"]), key=lambda r: r["n_tokens"])
    ok = [r for r in base[(b, q)] if r["correct"]]
    bs = max(ok, key=lambda r: r["n_tokens"]) if ok else max(base[(b, q)], key=lambda r: r["n_tokens"])
    think = bs["completion"].split("</think>")[0]
    tok_per_char = bs["n_tokens"] / max(1, len(bs["completion"]))
    m = re.search(rf"(?<![\w.]){re.escape(ans)}(?![\w.])", think, re.I)
    first = round(m.start() * tok_per_char) if m else None
    s = {"tag": tag, "bench": b, "qid": q, "answer": ans, "tl_tokens": t["n_tokens"], "base_tokens": bs["n_tokens"],
         "base_outcome": "correct" if bs["correct"] else ("cut off at 81,920 tokens, no answer" if not bs["finished"] else "wrong"),
         "base_first_answer_token": first, "base_waits": len(re.findall(r"\bWait\b", think)),
         "tl_waits": len(re.findall(r"\bWait\b", t["completion"].split("</think>")[0])),
         "base_answer_mentions": len(re.findall(rf"(?<![\w.]){re.escape(ans)}(?![\w.])", think, re.I))}
    stats[tag] = s
    q_text = t["prompt"].split("<|im_start|>user\n")[-1].split("<|im_end|>")[0].strip()
    (OUT / f"{tag}_question.txt").write_text(q_text, encoding="utf-8")
    (OUT / f"{tag}_thinkless.txt").write_text(t["completion"], encoding="utf-8")
    (OUT / f"{tag}_base.txt").write_text(bs["completion"], encoding="utf-8")
    print(json.dumps(s))
(OUT.parent.parent / "example_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
