"""Rejection sampling -> SFT data: per question, keep the shortest answer that is correct and finished."""
import json
import sys
from statistics import mean


def select_shortest_correct(records):
    best = {}
    for r in records:
        if r["correct"] and r["finished"] and (r["qid"] not in best or r["n_tokens"] < best[r["qid"]]["n_tokens"]):
            best[r["qid"]] = r
    return best


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    records = [json.loads(line) for line in open(src)]
    best = select_shortest_correct(records)
    with open(dst, "w") as f:
        for r in best.values():
            f.write(json.dumps({"prompt": r["prompt"], "completion": r["completion"]}) + "\n")
    correct = [r["n_tokens"] for r in records if r["correct"] and r["finished"]]
    print(f"questions kept: {len(best)} / {len({r['qid'] for r in records})}")
    print(f"mean tokens, all correct samples: {mean(correct):.0f}; selected shortest: "
          f"{mean(r['n_tokens'] for r in best.values()):.0f}")
