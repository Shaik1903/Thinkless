from reward import REWARD_FUNCS, accuracy_length_reward, accuracy_length_score


def total_reward(completions, n_tokens, answers):
    ids = [[1] * n for n in n_tokens]
    kinds = ["math"] * len(completions)
    per_func = [f(completions=completions, completion_ids=ids, answer=answers, kind=kinds) for f in REWARD_FUNCS]
    return [sum(vals) for vals in zip(*per_func)]


def test_wrong_is_zero_regardless_of_length():
    assert accuracy_length_score(False, 10) == 0.0


def test_shorter_correct_beats_longer_correct():
    assert accuracy_length_score(True, 500) > accuracy_length_score(True, 4000) > 0.0


def test_length_is_capped_and_never_negative():
    assert accuracy_length_score(True, 50_000) == accuracy_length_score(True, 8192) == 0.5


def test_trl_wrapper_shapes():
    out = accuracy_length_reward([r"a</think>\boxed{2}", r"a</think>\boxed{5}"], [[1] * 100, [1] * 100],
                                 answer=[r"\boxed{2}", r"\boxed{2}"], kind=["math", "math"])
    assert out[0] > 0 and out[1] == 0.0


def test_quick_wrong_guess_earns_nothing_total():
    # a fast, well-formatted wrong guess must not out-score an honest attempt that ran out of tokens
    guess, truncated = total_reward([r"</think>\boxed{9}", "still thinking..."], [20, 8192], [r"\boxed{2}"] * 2)
    assert guess == 0.0 and truncated == 0.0
