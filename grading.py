"""The single source of truth for right/wrong. Used by evals, SFT data selection and the GRPO reward."""
import os
import re

from math_verify import parse, verify

from data import Problem, last_boxed

# math-verify's timeouts use signals on Linux (the real pipeline) but subprocesses on Windows,
# which break there; timeouts only matter for pathological LaTeX, so skip them on Windows (local tests).
_TIMEOUT = None if os.name == "nt" else 5


def answer_part(completion: str, thinking: bool) -> str | None:
    """Text that counts as the final answer. None means the model never finished thinking."""
    if "</think>" in completion:
        return completion.split("</think>")[-1]
    return None if thinking else completion


def boxed_letter(box: str) -> str | None:
    """'\\boxed{\\textbf{(B)}}', '\\boxed{B. 42 kJ}' -> 'B'. None unless the box starts with a lone A-D."""
    inner = re.sub(r"\\[a-zA-Z]+", " ", box[len("\\boxed{"):-1])  # drop \text, \textbf, \mathrm ...
    words = re.sub(r"[^A-Za-z0-9]", " ", inner).split()
    return words[0] if words and words[0] in ("A", "B", "C", "D") else None


def is_correct(p: Problem, completion: str, thinking: bool = True) -> bool:
    ans = answer_part(completion, thinking)
    if ans is None:
        return False
    box = last_boxed(ans)
    if p.kind == "mcq":
        return box is not None and boxed_letter(box) == p.answer
    if box is None:
        return False
    try:
        return verify(parse(p.answer, parsing_timeout=_TIMEOUT), parse(box, parsing_timeout=_TIMEOUT),
                      timeout_seconds=_TIMEOUT)
    except Exception:  # math-verify can raise on malformed LaTeX; malformed = wrong
        return False
