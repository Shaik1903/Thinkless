"""Generate completions with vLLM, grade them, write one JSON line per sample."""
import argparse
import json

from transformers import AutoTokenizer
from vllm import LLM, SamplingParams

from data import SAMPLES, build_prompt, load_eval, load_sft_problems
from grading import answer_part, boxed_letter, is_correct
from data import last_boxed


def sampling(n: int, max_tokens: int, thinking: bool) -> SamplingParams:
    # Qwen3.5-2B model card "best practices" for text tasks. Reproducibility comes from LLM(seed=...).
    if thinking:
        return SamplingParams(n=n, temperature=1.0, top_p=0.95, top_k=20, presence_penalty=1.5, max_tokens=max_tokens)
    return SamplingParams(n=n, temperature=1.0, top_p=1.0, top_k=20, presence_penalty=2.0, max_tokens=max_tokens)


# Qwen's documented "thinking budget" recipe: when thinking is cut off at the budget, close it and force an answer
FORCE = "\n\nConsidering the limited time, I have to give the solution based on the thinking directly now.\n</think>\n\n"
# Multiple choice: after the forced close, models often kept deliberating in the answer (only 17/396 base GPQA
# answers boxed a letter within 1,024 tokens). Step 1 is the same free answer as for math; step 2, only for answers
# that never committed to a letter, pre-fills the answer's start (as s1's budget forcing appends "Final Answer:").
MCQ_PREFILL = "\n\nThe answer is \\boxed{"


def _letter(completion: str) -> str | None:
    box = last_boxed(answer_part(completion, True) or "")
    return boxed_letter(box) if box else None


def budget_forced(llm, jobs, budgets, out, thinking):
    """For each budget B: think up to B tokens; if thinking didn't finish, append FORCE and let the model answer
    (up to 1,024 more tokens). Every question gets an answer at every budget. Bench label: '<set>@<B>'."""
    with open(out, "w") as f:
        for b in budgets:
            outs = llm.generate([j[2] for j in jobs], [sampling(j[3].n, b, thinking) for j in jobs])
            done, cut = [], []
            for (name, p, prompt, _), o in zip(jobs, outs):
                for k, c in enumerate(o.outputs):
                    rec = {"bench": f"{name}@{b}", "qid": p.qid, "sample": k, "prompt": prompt, "completion": c.text,
                           "n_tokens": len(c.token_ids), "finished": c.finish_reason == "stop", "forced": False}
                    if "</think>" in c.text:
                        rec["correct"] = is_correct(p, c.text, thinking)
                        done.append(rec)
                    else:
                        cut.append((p, rec))
            if cut:
                answers = llm.generate([r["prompt"] + r["completion"] + FORCE for _, r in cut], sampling(1, 1024, thinking))
                for (p, rec), o in zip(cut, answers):
                    c = o.outputs[0]
                    rec.update(completion=rec["completion"] + FORCE + c.text, n_tokens=rec["n_tokens"] + len(c.token_ids),
                               finished=c.finish_reason == "stop", forced=True, prefilled=False)
                uncommitted = [(p, r) for p, r in cut if p.kind == "mcq" and _letter(r["completion"]) is None]
                if uncommitted:  # step 2 (multiple choice only): make the model commit to a letter
                    tails = llm.generate([r["prompt"] + r["completion"] + MCQ_PREFILL for _, r in uncommitted],
                                         sampling(1, 16, thinking))
                    for (p, rec), o in zip(uncommitted, tails):
                        c = o.outputs[0]
                        rec.update(completion=rec["completion"] + MCQ_PREFILL + c.text,
                                   n_tokens=rec["n_tokens"] + len(c.token_ids), prefilled=True)
                for p, rec in cut:
                    rec["correct"] = is_correct(p, rec["completion"], thinking)
                    done.append(rec)
            for rec in done:
                f.write(json.dumps(rec) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--sets", nargs="+", required=True, help="eval set names, or 'sft'")
    ap.add_argument("--n", type=int, help="override samples per problem")
    ap.add_argument("--max-tokens", type=int, default=81920)  # Qwen3.5 card: up to 81,920 for hard problems
    ap.add_argument("--no-thinking", action="store_true")
    ap.add_argument("--limit", type=int, help="only the first N problems per set (smoke tests)")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget-force", type=int, nargs="+", help="thinking budgets for the budget-forced eval")
    a = ap.parse_args()
    thinking = not a.no_thinking

    tok = AutoTokenizer.from_pretrained(a.model)
    # bf16 pinned: trained checkpoints are saved in fp32, and vLLM's "auto" would pick fp16 for those
    # budget forcing re-feeds prompt + B thinking tokens + FORCE, then answers (1,024): long GPQA prompts overflowed
    # the +2,048 headroom at B = 16k (18,433 > 18,432 tokens), so give it +8,192
    llm = LLM(a.model, dtype="bfloat16", max_model_len=a.max_tokens + (8192 if a.budget_force else 2048),
              gpu_memory_utilization=0.9, seed=a.shard)

    # One generate() call for all sets, so the GPU never idles waiting for one set's slowest answer.
    jobs = []  # (set name, problem, prompt, sampling params)
    for name in a.sets:
        if name == "sft":
            problems = load_sft_problems()
        elif name in ("sft_retry", "sft_teacher"):  # still-unsolved SFT problems: retry (16k) / teacher fill-in
            ids = set(open(f"data/{name}_qids.txt").read().split())
            problems = [p for p in load_sft_problems() if p.qid in ids]
        else:
            problems = load_eval(name)
        params = sampling(a.n or SAMPLES.get(name, 1), a.max_tokens, thinking)
        jobs += [(name, p, build_prompt(tok, p, thinking), params)
                 for p in problems[:a.limit][a.shard::a.num_shards]]
    if a.budget_force:
        return budget_forced(llm, jobs, a.budget_force, a.out, thinking)
    outs = llm.generate([j[2] for j in jobs], [j[3] for j in jobs])

    with open(a.out, "w") as f:
        for (name, p, prompt, _), o in zip(jobs, outs):
            for k, c in enumerate(o.outputs):
                f.write(json.dumps({
                    "bench": name, "qid": p.qid, "sample": k, "prompt": prompt, "completion": c.text,
                    "n_tokens": len(c.token_ids), "finished": c.finish_reason == "stop",
                    "correct": is_correct(p, c.text, thinking)}) + "\n")


if __name__ == "__main__":
    # skip vLLM's teardown in both outcomes: on 2026-09-30 it hung two finished awq_eval workers and one crashed
    # budget-force worker, each holding ~75 GB of GPU memory and blocking sharded.sh forever
    import os
    import traceback
    try:
        main()
    except BaseException:
        traceback.print_exc()
        os._exit(1)
    os._exit(0)
