from check_overlap import contaminated
from data import Problem


def test_detects_shared_13_gram_and_exact_match():
    long_q = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen"
    train = [Problem("t1", "Prefix words " + long_q, "x", "math"),
             Problem("t2", "What is 2+2?", "x", "math"),
             Problem("t3", "Completely unrelated question about apples and oranges", "x", "math")]
    assert sorted(contaminated(train, [long_q, "what is 2+2?"])) == ["t1", "t2"]
