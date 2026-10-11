"""Write the model card's Examples section (base vs ThinkLess) from release/ThinkLess-2B/examples/*.txt + stats.

Base outputs are 23k-82k tokens, so each example shows: a comparison table, what happened (verified by reading the
outputs), ThinkLess's full output and base excerpts in collapsible blocks, and links to both full outputs.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
EX = HERE / "ThinkLess-2B" / "examples"
S = json.loads((HERE / "example_stats.json").read_text(encoding="utf-8"))
ORDER = [
    ("gsm8k-A1", "GSM8K: same answer, 52x fewer tokens",
     "The base model worked out 30 − 19 = 11 within its first ~1,100 tokens (*\"Is that it? It seems too simple.\"*), "
     "then second-guessed the wording for another 44,000 tokens and 249 *\"Wait\"*s before answering 11. "
     "ThinkLess solves it once and stops."),
    ("math500-B1", "MATH-500: the base model never answers",
     "The base model sets up the clockwise turns correctly, then falls into a loop of re-checking and finally prints "
     "*\"Wait.\"* thousands of times (6,478 in total) until it hits the 81,920-token limit without an answer. "
     "ThinkLess reduces 2,250° to 90° past six full turns and answers."),
    ("math500-A1", "MATH-500: same answer, 15x fewer tokens",
     "The base model had 6 × 7 = 42 by ~token 1,900 (*\"Hold on. Is there any ambiguity?\"*), then spent 22,000 more "
     "tokens and 82 *\"Wait\"*s re-checking before answering 42. ThinkLess answers in 1,629 tokens."),
]


def clip(text, n):
    return text if len(text) <= n else text[:n].rsplit("\n", 1)[0]


def excerpt(base):
    think = base.split("</think>")[0]
    start = clip(think, 1500)
    mid_at = len(think) // 2
    middle = clip(think[mid_at:mid_at + 900], 700)
    end = base[-700:].split("\n", 1)[-1]
    return (f"{start}\n\n[... {len(think[len(start):mid_at]):,} characters omitted ...]\n\n{middle}\n\n"
            f"[... {len(base) - mid_at - len(middle) - len(end):,} characters omitted ...]\n\n{end}")


parts = ["## Examples", "",
         "Same question, same sampling settings, 81,920-token budget. The base model's outputs are too long to print, so "
         "each example shows the comparison, ThinkLess's full answer, and base excerpts; the full outputs of both models "
         "are in [`examples/`](examples/).", ""]
for i, (tag, title, story) in enumerate(ORDER, 1):
    s = S[tag]
    q = (EX / f"{tag}_question.txt").read_text(encoding="utf-8").split("\n\nPlease reason step by step")[0].strip()
    tl = (EX / f"{tag}_thinkless.txt").read_text(encoding="utf-8").strip()
    base = (EX / f"{tag}_base.txt").read_text(encoding="utf-8").strip()
    base_out = "cut off at the limit, **no answer**" if "cut off" in s["base_outcome"] else f"{s['answer']} (correct)"
    parts += [
        f"### Example {i}. {title}", "",
        f"**Question:** {q}", "",
        "| | Qwen3.5-2B (base) | **ThinkLess-2B** |",
        "|---|---|---|",
        f"| Tokens | {s['base_tokens']:,} | **{s['tl_tokens']:,}** ({s['base_tokens'] / s['tl_tokens']:.0f}x fewer) |",
        f"| Answer | {base_out} | **{s['answer']} (correct)** |",
        f"| \"Wait\" in the reasoning | {s['base_waits']:,} | {s['tl_waits']} |", "",
        f"**What happened:** {story}", "",
        f"<details><summary><b>ThinkLess-2B: full output ({s['tl_tokens']:,} tokens)</b></summary>", "",
        "```text", tl, "```", "", "</details>", "",
        f"<details><summary><b>Qwen3.5-2B (base): excerpts from {s['base_tokens']:,} tokens</b></summary>", "",
        "```text", excerpt(base), "```", "", "</details>", "",
        f"Full outputs: [base]({'examples/' + tag + '_base.txt'}) · [ThinkLess]({'examples/' + tag + '_thinkless.txt'})", "",
    ]
(HERE / "examples_section.md").write_text("\n".join(parts), encoding="utf-8")
for p in EX.glob("gsm8k-B1_*"):  # candidate not used in the card
    p.unlink()
print("examples section:", sum(len(p) for p in parts), "chars")
