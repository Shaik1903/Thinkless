from metrics import paired_diff, summarize


def rec(correct, n, finished=True, bench="b", qid=None):
    return {"bench": bench, "qid": qid or str(n), "correct": correct, "n_tokens": n, "finished": finished}


def test_summary_numbers():
    m = summarize([rec(True, 1000), rec(True, 5000), rec(False, 32768, finished=False), rec(False, 200)],
                  budgets=(2048, 8192))["b"]
    assert m["n"] == 4
    assert m["accuracy"] == 0.5
    assert m["mean_tokens"] == (1000 + 5000 + 32768 + 200) / 4
    assert m["truncation_rate"] == 0.25
    assert m["budget_accuracy"] == {"2048": 0.25, "8192": 0.5}


def test_benches_are_separate():
    out = summarize([rec(True, 10, bench="x"), rec(False, 10, bench="y")])
    assert out["x"]["accuracy"] == 1.0 and out["y"]["accuracy"] == 0.0


def test_paired_diff_per_problem_with_budget():
    ref = [rec(True, 9000, qid="a"), rec(True, 100, qid="a"), rec(True, 100, qid="b"), rec(False, 100, qid="b")]
    new = [rec(True, 50, qid="a"), rec(True, 50, qid="a"), rec(False, 50, qid="b"), rec(False, 50, qid="b")]
    # ref at an 8192 budget: a = 0.5 (9000 > budget), b = 0.5 -> 0.5; new: a = 1.0, b = 0.0 -> 0.5
    d = paired_diff(ref, new, budget=8192)
    assert d["diff"] == 0.0
    assert d["n_problems"] == 2
    lo, hi = d["ci95"]
    assert lo <= 0.0 <= hi


def test_paired_diff_ignores_problems_missing_from_either_side():
    d = paired_diff([rec(True, 10, qid="a"), rec(True, 10, qid="z")], [rec(False, 10, qid="a")])
    assert d["n_problems"] == 1 and d["diff"] == -1.0


def test_bootstrap_ci_brackets_accuracy_and_collapses_when_certain():
    mixed = summarize([rec(i % 2 == 0, 100, qid=f"q{i}") for i in range(40)])["b"]
    lo, hi = mixed["accuracy_ci95"]
    assert lo < mixed["accuracy"] < hi
    assert summarize([rec(True, 100, qid=f"q{i}") for i in range(10)])["b"]["accuracy_ci95"] == [1.0, 1.0]


def test_collapsed_on_the_real_run():
    from metrics import collapsed
    # rewards of the 2026-09-30 fixed GRPO run, steps 1-19 (step 17 ~0.39); it collapsed at steps 18-19
    run = [0.382, 0.432, 0.383, 0.406, 0.350, 0.403, 0.460, 0.428, 0.412, 0.469,
           0.474, 0.481, 0.470, 0.438, 0.445, 0.408, 0.39, 0.350, 0.142]
    assert not any(collapsed(run[:i]) for i in range(1, 19))  # healthy steps never trigger
    assert collapsed(run)  # step 19 does
