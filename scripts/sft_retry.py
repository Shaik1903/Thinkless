"""Problems with no correct, finished answer in the 8k pass -> data/sft_retry_qids.txt (retried at 16k).

Usage: python scripts/sft_retry.py data/sft_samples.jsonl
"""
import json
import sys
from collections import Counter

from data import load_sft_problems

recs = [json.loads(line) for line in open(sys.argv[1])]
solved = {r["qid"] for r in recs if r["correct"] and r["finished"]}
problems = load_sft_problems()
missing = [p.qid for p in problems if p.qid not in solved]
open("data/sft_retry_qids.txt", "w").write("\n".join(missing))

src = lambda qid: "gsm8k" if qid.startswith("gsm8k") else "math-" + qid.split("-")[2]
tot, kept = Counter(src(p.qid) for p in problems), Counter(src(q) for q in solved)
print(f"8k pass kept {len(solved)}/{len(problems)} ({len(solved) / len(problems):.0%}); retrying {len(missing)} at a larger budget")
for s in sorted(tot):
    print(f"  {s:32s} kept {kept[s]:5d}/{tot[s]:5d} ({kept[s] / tot[s]:.0%})")
