from data import Problem, last_boxed
from grading import is_correct

M = lambda ans: Problem("q", "question", ans, "math")
C = lambda letter: Problem("q", "question", letter, "mcq")


def test_last_boxed_handles_nested_braces():
    assert last_boxed(r"x \boxed{1} then \boxed{\frac{1}{2}} end") == r"\boxed{\frac{1}{2}}"
    assert last_boxed("no box here") is None


def test_correct_math_after_think():
    assert is_correct(M(r"\boxed{72}"), r"so 72</think>The answer is \boxed{72}.")


def test_equivalent_forms_are_correct():
    assert is_correct(M(r"\boxed{\frac{1}{2}}"), r"...</think>\boxed{0.5}")
    assert is_correct(M(r"\boxed{72}"), r"...</think>\boxed{72.0}")


def test_wrong_answer():
    assert not is_correct(M(r"\boxed{72}"), r"...</think>\boxed{73}")


def test_unfinished_thinking_is_wrong_even_with_box_inside():
    assert not is_correct(M(r"\boxed{72}"), r"maybe \boxed{72}? let me check again and again")


def test_box_only_inside_thinking_is_wrong():
    assert not is_correct(M(r"\boxed{72}"), r"I get \boxed{72}</think>The answer is 72.")


def test_thinking_off_reads_whole_text():
    assert is_correct(M(r"\boxed{72}"), r"The answer is \boxed{72}.", thinking=False)


def test_mcq_letter():
    assert is_correct(C("B"), r"...</think>\boxed{B}")
    assert is_correct(C("B"), r"...</think>\boxed{(B)}")
    assert not is_correct(C("B"), r"...</think>\boxed{C}")


def test_mcq_letter_formatting_variants():
    for boxed_answer in [r"\boxed{\text{B}}", r"\boxed{\textbf{(B)}}", r"\boxed{B)}", r"\boxed{B. 42 kJ}",
                         r"\boxed{\mathrm{B}}", r"\boxed{ $B$ }"]:
        assert is_correct(C("B"), "...</think>" + boxed_answer), boxed_answer
    assert not is_correct(C("B"), r"...</think>\boxed{Both}")
    assert not is_correct(C("B"), r"...</think>\boxed{42}")
