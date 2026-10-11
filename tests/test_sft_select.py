from build_sft_data import select_shortest_correct


def r(qid, correct, n, finished=True):
    return {"qid": qid, "correct": correct, "n_tokens": n, "finished": finished, "prompt": "p", "completion": f"c{n}"}


def test_picks_shortest_correct_finished_one_per_question():
    best = select_shortest_correct([r("a", True, 900), r("a", True, 300), r("a", False, 100),
                                    r("a", True, 200, finished=False), r("b", False, 50)])
    assert set(best) == {"a"}
    assert best["a"]["n_tokens"] == 300
