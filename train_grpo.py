"""Stage 2: GRPO with the accuracy-length reward. Resumable; stops itself after MAX_HOURS.

Sparse-reward safeguard: if the mean reward over the first GUARD_STEPS steps is below GUARD_MIN, the run writes
{out}/SPARSE_REWARD and stops, so the pipeline can restart once with easier problems mixed in (GRPO_MIX_MATH=1).
"""
import os
import random
import sys
import time
from pathlib import Path

from datasets import Dataset
from transformers import AutoTokenizer, TrainerCallback
from transformers.trainer_utils import get_last_checkpoint
from trl import GRPOConfig, GRPOTrainer

from data import build_prompt, load_grpo_problems, load_math_rl_problems
from grpo_budget import decide_from_files
from metrics import collapsed

# Completion cap decided from the SFT model's own eval (8k, or 12k if >=25% of its correct answers need more than 8k).
# Must be set before `reward` is imported: the length penalty is scaled to the same cap.
BUDGET = decide_from_files() if "MAX_COMPLETION" not in os.environ else {"max_len": int(os.environ["MAX_COMPLETION"])}
os.environ["GRPO_MAX_LEN"] = str(BUDGET["max_len"])
# 12k completions need more training memory: give vLLM 0.10 less than the pipeline's setting (0.35 -> 0.25, OOM retry 0.15)
VLLM_MEM = float(os.environ.get("VLLM_GPU_MEM", 0.35)) - (0.10 if BUDGET["max_len"] > 8192 else 0.0)
print(f"GRPO completion budget: {BUDGET} | vLLM memory share {VLLM_MEM:.2f}")

from reward import MAX_LEN, REWARD_FUNCS  # noqa: E402

model, out = sys.argv[1], sys.argv[2]
# start from a given checkpoint instead of SFT (used to resume after the collapse)
model = os.environ.get("GRPO_INIT", model)
MAX_HOURS = float(os.environ.get("MAX_HOURS", 6))
# mix easier MATH L3-5 problems into DAPO
MIX_MATH = os.environ.get("GRPO_MIX_MATH") == "1" or Path("state/grpo_mix_math").exists()
# MATH only: just 13% of DAPO answers finished within the 12k cap
MATH_ONLY = Path("state/grpo_math_only").exists()
GUARD_STEPS, GUARD_MIN = int(os.environ.get("GUARD_STEPS", 30)), float(os.environ.get("GUARD_MIN", 0.02))


class TimeLimit(TrainerCallback):
    """Save and stop once the wall-clock budget is used (budget control)."""
    def __init__(self):
        self.t0 = time.time()

    def on_step_end(self, args, state, control, **kwargs):
        # touch state/grpo_stop to end early without failing the stage
        if time.time() - self.t0 > MAX_HOURS * 3600 or Path("state/grpo_stop").exists():
            control.should_save = True
            control.should_training_stop = True


class SparseRewardGuard(TrainerCallback):
    """Stop early if almost no answer earns reward: GRPO can't learn from all-zero groups."""
    def __init__(self):
        self.rewards = []

    def on_log(self, args, state, control, logs=None, **kwargs):
        if MIX_MATH or MATH_ONLY or logs is None or "reward" not in logs or state.global_step > GUARD_STEPS:
            return
        self.rewards.append(float(logs["reward"]))
        if state.global_step == GUARD_STEPS and sum(self.rewards) / len(self.rewards) < GUARD_MIN:
            if state.is_world_process_zero:
                Path(out).mkdir(parents=True, exist_ok=True)
                Path(out, "SPARSE_REWARD").write_text(f"mean reward {sum(self.rewards) / len(self.rewards):.4f} "
                                                      f"over first {GUARD_STEPS} steps\n")
            control.should_training_stop = True


class NoUpdateGuard(TrainerCallback):
    """Fail loudly if the model isn't being updated (3 logged steps in a row with grad_norm < 1e-6)."""
    def __init__(self):
        self.zero = 0

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None or "grad_norm" not in logs:
            return
        self.zero = self.zero + 1 if float(logs["grad_norm"]) < 1e-6 else 0
        if self.zero >= 3:
            raise RuntimeError(f"grad_norm < 1e-6 for 3 steps (last {logs['grad_norm']}): the model is not learning")


class CollapseGuard(TrainerCallback):
    """Save and stop if reward collapses (metrics.collapsed). The 2026-09-30 run went 0.48 -> 0.14 in 3 steps as the
    text degenerated into word salad and loops; the pipeline then continues with the best healthy checkpoint."""
    def __init__(self):
        self.rewards = []

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None or "reward" not in logs:
            return
        self.rewards.append(float(logs["reward"]))
        if collapsed(self.rewards):
            if state.is_world_process_zero:
                Path(out, "COLLAPSE").write_text(f"step {state.global_step}: rewards {self.rewards[-5:]}\n")
            control.should_save = True
            control.should_training_stop = True


tok = AutoTokenizer.from_pretrained(model)
problems = load_math_rl_problems() if MATH_ONLY else load_grpo_problems() + (load_math_rl_problems() if MIX_MATH else [])
random.Random(0).shuffle(problems)
ds = Dataset.from_list([{"prompt": build_prompt(tok, p), "answer": p.answer, "kind": p.kind} for p in problems])
print(f"GRPO problems: {len(ds)} (MATH L3-5 only: {MATH_ONLY}; mixed into DAPO: {MIX_MATH})")

cfg = GRPOConfig(
    output_dir=out, run_name="thinkless-grpo",
    learning_rate=1e-6, lr_scheduler_type="constant_with_warmup", warmup_steps=5,
    # 1 completion per forward pass (8k-token logits over a 248k vocab are large); 1 x 64 x 8 GPUs = 512
    per_device_train_batch_size=1, gradient_accumulation_steps=64, num_generations=8,
    # fp32 master weights + bf16 autocast: at lr 1e-6, pure-bf16 weights would round every update to zero
    model_init_kwargs={"dtype": "float32"},
    max_completion_length=MAX_LEN,
    # on-policy sampling from the model itself: Qwen's inference settings (presence penalty 1.5, top-k 20, top-p 0.95)
    # are not in vLLM's raw logprobs, so the trainer can't correct for them; the first run drifted into word salad
    temperature=1.0, top_p=1.0, top_k=0,
    use_vllm=True, vllm_mode="colocate", vllm_enable_sleep_mode=True,
    # TRL's default "sequence_mask" multiplies per-token vLLM/trainer ratios over the whole answer: at 8-12k tokens the
    # product falls outside [1/3, 3], every answer is masked, and grad_norm is ~1e-9 (no learning). Per-token ratios
    # clipped at 3 (truncated importance sampling) keep the correction without masking whole answers.
    vllm_importance_sampling_mode="token_truncate",
    vllm_gpu_memory_utilization=VLLM_MEM,  # pipeline retries at 0.10 less on OOM
    # small KL anchor to the starting model (0 in the collapsed run): keeps the policy from drifting into degenerate text
    beta=float(os.environ.get("GRPO_BETA", 0.01)), loss_type="dr_grpo", scale_rewards=False,
    bf16=True, gradient_checkpointing=True,
    # Qwen3.5's vision tower gets no gradient on text; multi-GPU DDP must be told to expect that
    ddp_find_unused_parameters=True,
    max_steps=int(os.environ.get("MAX_STEPS", 1000)), save_steps=int(os.environ.get("SAVE_STEPS", 5)),  # ~13 min at ~160 s/step
    logging_steps=1, log_completions=True, report_to="wandb",
)
trainer = GRPOTrainer(model=model, reward_funcs=REWARD_FUNCS, args=cfg,
                      train_dataset=ds, processing_class=tok, callbacks=[TimeLimit(), SparseRewardGuard(), NoUpdateGuard(), CollapseGuard()])
dtype = next(trainer.model.parameters()).dtype
print("weight dtype:", dtype)
assert str(dtype) == "torch.float32", "weights must be fp32 (see model_init_kwargs); bf16 weights lose updates"
trainer.train(resume_from_checkpoint=get_last_checkpoint(out) if os.path.isdir(out) else None)
trainer.save_model(f"{out}/final")
