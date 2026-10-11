"""Contamination check: drop training problems that share a 13-word span (or exact text) with any eval problem."""
import re


def _norm(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def _ngrams(text, n):
    words = _norm(text).split()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def contaminated(train, eval_questions, n=13):
    exact = {_norm(q) for q in eval_questions}
    grams = set().union(*(_ngrams(q, n) for q in eval_questions))
    return [p.qid for p in train if _norm(p.question) in exact or _ngrams(p.question, n) & grams]


if __name__ == "__main__":
    from data import DROP_FILE, EVAL_SETS, load_eval, load_grpo_problems, load_sft_problems
    DROP_FILE.unlink(missing_ok=True)  # evaluate against the full training pools
    eval_qs = [p.question for name in EVAL_SETS for p in load_eval(name)]
    train = load_sft_problems() + load_grpo_problems()
    bad = contaminated(train, eval_qs)
    DROP_FILE.parent.mkdir(exist_ok=True)
    DROP_FILE.write_text("\n".join(bad))
    print(f"dropping {len(bad)} of {len(train)} training problems -> {DROP_FILE}")
