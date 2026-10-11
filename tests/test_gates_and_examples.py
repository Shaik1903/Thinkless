from check_gates import baseline_problems, sft_problems
from export_examples import pick_showcase


def m(acc, lo, hi):
    return {"accuracy": acc, "accuracy_ci95": [lo, hi]}


def test_baseline_gate_passes_when_close_or_within_ci():
    assert baseline_problems({"gpqa": m(0.50, 0.45, 0.55), "hmmt25": m(0.21, 0.12, 0.30)}) == []
    # 8 points off but the published score is inside our CI (small, noisy set): not a harness bug
    assert baseline_problems({"gpqa": m(0.50, 0.45, 0.55), "hmmt25": m(0.15, 0.05, 0.25)}) == []


def test_baseline_gate_fails_when_far_off_and_outside_ci():
    problems = baseline_problems({"gpqa": m(0.40, 0.35, 0.45), "hmmt25": m(0.22, 0.12, 0.30)})
    assert len(problems) == 1 and "gpqa" in problems[0]


def test_sft_gate():
    base = {"math500": {"accuracy": 0.80}}
    assert sft_problems(base, {"math500": {"accuracy": 0.78}}) == []
    assert len(sft_problems(base, {"math500": {"accuracy": 0.76}})) == 1


def test_grpo_gpqa_gate():
    sft = {"gpqa": {"accuracy": 0.548}}
    assert sft_problems(sft, {"gpqa": {"accuracy": 0.53}}, bench="gpqa", names=("GRPO", "SFT")) == []
    fail = sft_problems(sft, {"gpqa": {"accuracy": 0.51}}, bench="gpqa", names=("GRPO", "SFT"))
    assert len(fail) == 1 and fail[0].startswith("gpqa: GRPO 0.510 vs SFT 0.548")


def r(qid, correct, n, finished=True, completion="x</think>\\boxed{1}"):
    return {"bench": "math500", "qid": qid, "sample": 0, "correct": correct, "n_tokens": n,
            "finished": finished, "completion": completion}


def test_showcase_picks_both_correct_with_biggest_token_saving():
    base = [r("a", True, 6000), r("b", True, 3000), r("c", False, 8000), r("d", True, 900)]
    new = [r("a", True, 600), r("b", True, 1500), r("c", True, 700), r("d", True, 800)]
    picked = pick_showcase(base, new, k=2)
    assert [p["qid"] for p in picked] == ["a", "b"]           # 10x then 2x; c excluded (base wrong)
    assert picked[0]["base_tokens"] == 6000 and picked[0]["new_tokens"] == 600
