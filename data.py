"""Dataset loaders and prompt building. Every problem becomes a Problem with a checkable gold answer."""
import random
import re
from dataclasses import dataclass
from pathlib import Path

from datasets import load_dataset

MATH_SUFFIX = "Please reason step by step, and put your final answer within \\boxed{}."
MCQ_SUFFIX = "Think step by step, then put only the letter of the correct option (A, B, C or D) within \\boxed{}."
LEVELS = {"Level 3", "Level 4", "Level 5"}
MATH_SUBJECTS = ["algebra", "counting_and_probability", "geometry", "intermediate_algebra",
                 "number_theory", "prealgebra", "precalculus"]
DROP_FILE = Path("results/drop_train.txt")  # written by check_overlap.py


@dataclass(frozen=True)
class Problem:
    qid: str
    question: str
    answer: str  # math: "\\boxed{...}"; mcq: "A".."D"
    kind: str    # "math" or "mcq"


def last_boxed(text: str) -> str | None:
    """Return the last \\boxed{...} in text, braces balanced, or None."""
    start = text.rfind("\\boxed{")
    if start == -1:
        return None
    depth = 0
    for i in range(start + len("\\boxed"), len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def boxed(ans: str) -> str:
    return "\\boxed{" + ans.strip() + "}"


def _gsm8k(split):
    ds = load_dataset("openai/gsm8k", "main", split=split)
    return [Problem(f"gsm8k-{split}-{i}", r["question"],
                    boxed(r["answer"].split("####")[-1].replace(",", "")), "math")
            for i, r in enumerate(ds)]


def _math(split, levels):
    out = []
    for s in MATH_SUBJECTS:
        for i, r in enumerate(load_dataset("EleutherAI/hendrycks_math", s, split=split)):
            gold = last_boxed(r["solution"])
            if r["level"] in levels and gold:
                out.append(Problem(f"math-{split}-{s}-{i}", r["problem"], gold, "math"))
    return out


def _math500():
    ds = load_dataset("HuggingFaceH4/MATH-500", split="test")
    return [Problem(f"math500-{i}", r["problem"], boxed(r["answer"]), "math") for i, r in enumerate(ds)]


def _mathval(n=300):
    """Checkpoint-selection set: MATH test L3-5 problems that are NOT in MATH-500."""
    taken = {p.question for p in _math500()}
    pool = [p for p in _math("test", LEVELS) if p.question not in taken]
    random.Random(0).shuffle(pool)
    return pool[:n]


def _hmmt25():
    ds = load_dataset("MathArena/hmmt_feb_2025", split="train")
    return [Problem(f"hmmt25-{i}", r["problem"], boxed(str(r["answer"])), "math") for i, r in enumerate(ds)]


def _gpqa():
    ds = load_dataset("Idavidrein/gpqa", "gpqa_diamond", split="train")
    out = []
    for i, r in enumerate(ds):
        opts = [r["Correct Answer"], r["Incorrect Answer 1"], r["Incorrect Answer 2"], r["Incorrect Answer 3"]]
        order = list(range(4))
        random.Random(i).shuffle(order)  # fixed shuffle per question, so every model sees the same options
        body = "\n".join(f"{'ABCD'[k]}) {opts[j].strip()}" for k, j in enumerate(order))
        out.append(Problem(f"gpqa-{i}", f"{r['Question'].strip()}\n\n{body}", "ABCD"[order.index(0)], "mcq"))
    return out


EVAL_SETS = {"gsm8k": lambda: _gsm8k("test"), "math500": _math500, "mathval": _mathval,
             "hmmt25": _hmmt25, "gpqa": _gpqa}
SAMPLES = {"gsm8k": 1, "math500": 2, "mathval": 4, "hmmt25": 8, "gpqa": 2}


def load_eval(name: str) -> list[Problem]:
    return EVAL_SETS[name]()


def _drop(problems):
    drop = set(DROP_FILE.read_text().split()) if DROP_FILE.exists() else set()
    return [p for p in problems if p.qid not in drop]


def load_sft_problems() -> list[Problem]:
    return _drop(_gsm8k("train") + _math("train", LEVELS))


_DAPO_PREFIX = re.compile(r"^Solve the following math problem.*?\n\n", re.S)
_DAPO_SUFFIX = re.compile(r"\n\nRemember to put your answer.*$", re.S)


def clean_dapo(text: str) -> str:
    """DAPO prompts wrap each problem in its own answer-format instructions; strip them so we use ours."""
    return _DAPO_SUFFIX.sub("", _DAPO_PREFIX.sub("", text)).strip()


def load_grpo_problems(n: int = 6000, seed: int = 0) -> list[Problem]:
    ds = load_dataset("BytedTsinghua-SIA/DAPO-Math-17k", split="train")
    seen, out = set(), []
    for prompt, rm in zip(ds["prompt"], ds["reward_model"]):
        q = clean_dapo(prompt[0]["content"])
        if q not in seen:  # the dataset repeats each problem many times
            seen.add(q)
            out.append(Problem(f"dapo-{len(out)}", q, boxed(str(rm["ground_truth"])), "math"))
    random.Random(seed).shuffle(out)
    return _drop(out[:n])


def load_math_rl_problems() -> list[Problem]:
    """Easier GRPO fallback pool (MATH train L3-5), used only if DAPO rewards are too sparse."""
    return _drop(_math("train", LEVELS))


def build_prompt(tokenizer, p: Problem, thinking: bool = True) -> str:
    suffix = MCQ_SUFFIX if p.kind == "mcq" else MATH_SUFFIX
    msgs = [{"role": "user", "content": f"{p.question}\n\n{suffix}"}]
    return tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True,
                                         enable_thinking=thinking)
