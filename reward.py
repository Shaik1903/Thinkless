"""GRPO reward. Wrong or unfinished = 0; correct = 1 minus a length penalty.

No separate format bonus: a missing answer already scores 0 (same as wrong), and a bonus paid to
wrong-but-well-formatted answers would teach the model to stop thinking and guess.
"""
import os

from data import Problem
from grading import is_correct

LAMBDA = 0.5    # strength of the brevity push
MAX_LEN = int(os.environ.get("GRPO_MAX_LEN", 8192))  # equals GRPO max_completion_length (set by train_grpo.py)


def accuracy_length_score(correct: bool, n_tokens: int, lam: float = LAMBDA, max_len: int = MAX_LEN) -> float:
    if not correct:
        return 0.0
    return 1.0 - lam * min(n_tokens, max_len) / max_len


# TRL calls reward functions with the batch of completions plus every dataset column as a keyword list.
def accuracy_length_reward(completions, completion_ids, answer, kind, **kwargs):
    return [accuracy_length_score(is_correct(Problem("", "", a, k), c), len(ids))
            for c, ids, a, k in zip(completions, completion_ids, answer, kind)]


REWARD_FUNCS = [accuracy_length_reward]  # what train_grpo.py passes to GRPOTrainer
