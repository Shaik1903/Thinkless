"""Stage 1: full fine-tune on the model's own shortest correct answers."""
import os
import sys

from datasets import load_dataset
from transformers.trainer_utils import get_last_checkpoint
from trl import SFTConfig, SFTTrainer

model, data, out = sys.argv[1], sys.argv[2], sys.argv[3]
ds = load_dataset("json", data_files=data, split="train")

cfg = SFTConfig(
    output_dir=out, run_name="thinkless-sft",
    num_train_epochs=2, max_steps=int(os.environ.get("MAX_STEPS", -1)),
    learning_rate=1e-5, lr_scheduler_type="cosine", warmup_steps=0.05,  # float < 1 = ratio of total steps
    # batch 1: an 8k-token example's logits over a 248k vocab are ~8GB in fp32; x4 would not fit
    per_device_train_batch_size=1, gradient_accumulation_steps=16,
    # fp32 master weights + bf16 autocast: pure-bf16 weights would round tiny Adam updates to zero
    model_init_kwargs={"dtype": "float32"},
    # 17,408 = 16k retry-pass answers (hard problems keep their longer reasoning) + prompt
    max_length=int(os.environ.get("SFT_MAX_LEN", 17408)), bf16=True, gradient_checkpointing=True,
    # Qwen3.5's vision tower gets no gradient on text; multi-GPU DDP must be told to expect that
    ddp_find_unused_parameters=True,
    # checkpoint ~every 15 min (30 steps x ~15-28 s) so an interruption loses little; keep 2 for resuming
    logging_steps=5, save_strategy="steps", save_steps=int(os.environ.get("SAVE_STEPS", 30)), save_total_limit=2,
    report_to="wandb",
)
trainer = SFTTrainer(model=model, args=cfg, train_dataset=ds)

dtype = next(trainer.model.parameters()).dtype
print("weight dtype:", dtype)
assert str(dtype) == "torch.float32", "weights must be fp32 (see model_init_kwargs); bf16 weights lose updates"

first = trainer.train_dataset[0]
print("example ends with:", repr(trainer.processing_class.decode(first["input_ids"][-3:])))

trainer.train(resume_from_checkpoint=get_last_checkpoint(out) if os.path.isdir(out) else None)
trainer.save_model(out)
