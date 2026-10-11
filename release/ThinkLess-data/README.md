---
license: mit
language:
- en
task_categories:
- text-generation
tags:
- reasoning
- efficient-reasoning
- math
- chain-of-thought
- distillation
- evaluation
configs:
- config_name: sft
  data_files: sft/thinkless_sft.jsonl
  default: true
- config_name: rollouts_8k
  data_files: rollouts/rollouts_sft_samples.jsonl.gz
- config_name: rollouts_16k_retry
  data_files: rollouts/rollouts_sft_retry.jsonl.gz
- config_name: rollouts_9b_teacher
  data_files: rollouts/rollouts_sft_teacher.jsonl.gz
- config_name: eval_full_budget
  data_files: eval_outputs/full_budget/*.jsonl.gz
- config_name: eval_budget_forcing
  data_files: eval_outputs/budget_forcing/*.jsonl.gz
---

# ThinkLess-data

The data behind [ThinkLess-2B](https://huggingface.co/Shaik1903/ThinkLess-2B): the SFT set of short, correct
reasoning traces, every raw generation it was selected from, and every benchmark answer behind the reported numbers.

| Config | What it is | Rows |
|---|---|---|
| **`sft`** (default) | The SFT training set: the shortest correct solution per problem | 8,890 |
| `rollouts_8k` | All Qwen3.5-2B samples at an 8k-token budget, right and wrong | [ROWS_samples] |
| `rollouts_16k_retry` | Qwen3.5-2B retries at 16k for problems unsolved at 8k | [ROWS_retry] |
| `rollouts_9b_teacher` | Qwen3.5-9B attempts on problems the 2B never solved | [ROWS_teacher] |
| `eval_full_budget` | GSM8K + MATH-500 answers at the 81,920-token budget, for every model | [ROWS_eval_full] |
| `eval_budget_forcing` | GSM8K + MATH-500 answers under a hard thinking budget (2k–16k) | [ROWS_eval_bf] |

```python
from datasets import load_dataset
sft = load_dataset("Shaik1903/ThinkLess-data", "sft", split="train")
```

## `sft`: how it was built

![Share of problems with a correct solution after each data-generation pass](charts/sft_funnel.png)

![The 8,890 SFT examples by subject and source](charts/sft_composition.png)

1. **Problems:** GSM8K train and MATH train (levels 3–5), 12,936 problems after removing any 13-gram overlap with
   GSM8K test, MATH-500, GPQA-Diamond and HMMT Feb 2025.
2. **Candidates:** 4 samples per problem from Qwen3.5-2B (thinking mode) at an 8k-token cap (`rollouts_8k`); problems
   with no correct and finished answer got 4 more at 16k (`rollouts_16k_retry`); problems still unsolved got 2
   attempts from Qwen3.5-9B (`rollouts_9b_teacher`).
3. **Selection:** for each problem, the shortest correct and finished solution (graded with `math-verify`). GSM8K was
   capped at the number of MATH examples, keeping its shortest solutions.

| Source (`generator`) | Examples | Share |
|---|---|---|
| Qwen3.5-2B, 8k budget | 5,314 | 59.8% |
| Qwen3.5-2B, 16k retry | 959 | 10.8% |
| Qwen3.5-9B teacher | 2,617 | 29.4% |

By subject: GSM8K 4,445; MATH algebra 1,172, intermediate algebra 786, prealgebra 679, number theory 577, counting &
probability 459, geometry 430, precalculus 342. The data is **difficulty-adaptive**: short solutions for easy
problems (GSM8K mean ~2,000 tokens), longer ones for hard MATH subjects.

**Fields:** `id`, `source_dataset` (gsm8k / math), `subject`, `question`, `gold_answer` (`\boxed{…}`), `completion`
(`<think>` reasoning then the answer), `n_tokens`, `generator`.

## `rollouts_*`: every raw generation

Right and wrong, finished and cut off: useful for studying reasoning length and looping, rejection sampling, and
preference pairs (short-correct vs long or wrong answers to the same problem). Sampling: temperature 1.0, top-p 0.95,
top-k 20, presence penalty 1.5 (Qwen3.5's thinking-mode settings).

**Fields:** `bench` (sft / sft_retry / sft_teacher), `qid` (matches `id` in `sft`), `sample`, `prompt`, `completion`,
`n_tokens`, `finished` (false if cut off), `correct` (`math-verify`).

## `eval_*`: benchmark outputs

`eval_full_budget` files (GSM8K test 1,319 × 1 sample, MATH-500 500 × 2 samples): `base_thinking`, `base_no_thinking`,
`thinkless_sft`, `thinkless`, `thinkless_fp8`, `thinkless_awq` (the 4-bit version, evaluated but not released).
`eval_budget_forcing` files: `base`, `thinkless_sft`, `thinkless`; `bench` is `gsm8k@2048` … `math500@16384`, and
`forced` marks answers whose thinking was cut off at the budget.

**Not included:** GPQA-Diamond outputs, because the GPQA authors ask that its questions not be posted online (to
avoid leakage into training data), and HMMT Feb 2025 outputs, whose source dataset is share-alike licensed. Their
scores are reported in the model card.

**Fields:** `bench`, `qid`, `sample`, `prompt`, `completion`, `n_tokens`, `finished`, `correct`, and `forced`
(budget forcing).

## License and attribution

Problems from [GSM8K](https://huggingface.co/datasets/openai/gsm8k) (MIT), [MATH](https://github.com/hendrycks/math)
(MIT) and [MATH-500](https://huggingface.co/datasets/HuggingFaceH4/MATH-500) (MIT). Generations from
[Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B), Qwen3.5-9B (Apache-2.0) and the ThinkLess models. Released under
MIT.
