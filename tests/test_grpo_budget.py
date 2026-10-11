from grpo_budget import decide


def r(n, correct=True, bench="math500"):
    return {"n_tokens": n, "correct": correct, "bench": bench}


def test_keeps_8k_when_few_correct_answers_are_long():
    recs = [r(3000)] * 80 + [r(9000)] * 20 + [r(20000, correct=False)] * 50  # wrong answers ignored
    assert decide(recs)["max_len"] == 8192


def test_raises_to_12k_when_many_correct_answers_are_long():
    recs = [r(3000, bench="mathval")] * 70 + [r(9000, bench="mathval")] * 30
    d = decide(recs)
    assert d["max_len"] == 12288 and d["share_over_8k"] == 0.3


def test_only_math_benchmarks_count():
    assert decide([r(20000, bench="gpqa")] * 10 + [r(1000)] * 10)["max_len"] == 8192
