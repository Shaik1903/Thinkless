"""Package and upload the ThinkLess release to Hugging Face as private repos (run on the release VM).

~/release layout: models/ThinkLess-2B{,-SFT,-FP8} (weights), cards/<repo>/ (README, charts, examples), hf_token.
Datasets are rebuilt from the bucket; eval outputs keep GSM8K and MATH-500 only (GPQA authors ask that questions not
be posted online; HMMT's source is share-alike). Repos are created private.
"""
import gzip
import json
import shutil
import subprocess
from pathlib import Path

from huggingface_hub import HfApi

HOME = Path.home() / "release"
USER = "Shaik1903"
B = "gs://thinkless-sadikh/run/results"
KEEP = ("gsm8k", "math500")
api = HfApi(token=(HOME / "hf_token").read_text().strip())
assert api.whoami()["name"] == USER


def gs(src, dst):
    subprocess.run(["gcloud", "storage", "cp", src, str(dst), "--quiet"], check=True)


def filter_gz(src, dst, is_gz):
    n = 0
    opener = gzip.open if is_gz else open
    with opener(src, "rt", encoding="utf-8") as fin, gzip.open(dst, "wt", encoding="utf-8") as fout:
        for line in fin:
            if json.loads(line)["bench"].split("@")[0] in KEEP:
                fout.write(line)
                n += 1
    return n


def count_gz(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return sum(1 for _ in f)


def fill(readme, counts):
    s = readme.read_text(encoding="utf-8")
    for k, v in counts.items():
        s = s.replace(f"[ROWS_{k}]", f"{v:,}")
    assert "[ROWS_" not in s, [l for l in s.splitlines() if "[ROWS_" in l]
    readme.write_text(s, encoding="utf-8")


D = HOME / "datasets"
raw = D / "raw"
raw.mkdir(parents=True, exist_ok=True)
data = D / "ThinkLess-data"
for sub in ("sft", "rollouts", "eval_outputs/full_budget", "eval_outputs/budget_forcing"):
    (data / sub).mkdir(parents=True, exist_ok=True)


def fetch(src, dst):  # reuse files already downloaded by an earlier (stopped) run
    if not Path(dst).exists():
        gs(src, dst)


fetch(f"{B}/datasets/thinkless_sft.jsonl", data / "sft" / "thinkless_sft.jsonl")
counts = {}
for name, key in (("sft_samples", "samples"), ("sft_retry", "retry"), ("sft_teacher", "teacher")):
    fetch(f"{B}/datasets/rollouts_{name}.jsonl.gz", data / "rollouts" / f"rollouts_{name}.jsonl.gz")
    counts[key] = count_gz(data / "rollouts" / f"rollouts_{name}.jsonl.gz")
full = data / "eval_outputs" / "full_budget"
bf = data / "eval_outputs" / "budget_forcing"
counts["eval_full"] = 0
for src, out in (("base_think", "base_thinking"), ("base_nothink", "base_no_thinking"), ("sft", "thinkless_sft"),
                 ("grpo", "thinkless"), ("grpo_awq", "thinkless_awq")):
    fetch(f"{B}/datasets/eval_outputs_{src}.jsonl.gz", raw / f"{src}.jsonl.gz")
    counts["eval_full"] += filter_gz(raw / f"{src}.jsonl.gz", full / f"{out}.jsonl.gz", True)
fetch(f"{B}/grpo_fp8.jsonl", raw / "grpo_fp8.jsonl")
counts["eval_full"] += filter_gz(raw / "grpo_fp8.jsonl", full / "thinkless_fp8.jsonl.gz", False)
counts["eval_bf"] = 0
for src, out in (("base", "base"), ("sft", "thinkless_sft"), ("thinkless", "thinkless")):
    fetch(f"{B}/bforce_{src}.jsonl", raw / f"bforce_{src}.jsonl")
    counts["eval_bf"] += filter_gz(raw / f"bforce_{src}.jsonl", bf / f"{out}.jsonl.gz", False)
shutil.copy(HOME / "cards/ThinkLess-data/README.md", data / "README.md")
fill(data / "README.md", counts)
print("rows:", json.dumps(counts))

# models: add cards (README, charts, examples) next to the weights
for name in ("ThinkLess-2B", "ThinkLess-2B-SFT", "ThinkLess-2B-FP8"):
    shutil.copytree(HOME / "cards" / name, HOME / "models" / name, dirs_exist_ok=True)

# upload, private
repos = [("model", n, HOME / "models" / n) for n in ("ThinkLess-2B", "ThinkLess-2B-SFT", "ThinkLess-2B-FP8")] + \
        [("dataset", "ThinkLess-data", data)]
for kind, name, folder in repos:
    rid = f"{USER}/{name}"
    api.create_repo(rid, repo_type=kind, private=True, exist_ok=True)
    assert api.repo_info(rid, repo_type=kind).private, f"{rid} is not private"
    api.upload_folder(repo_id=rid, repo_type=kind, folder_path=str(folder), commit_message="ThinkLess release (private review)")
    print("uploaded", kind, rid)

# a private collection grouping everything
coll = api.create_collection(title="ThinkLess", namespace=USER, private=True, exists_ok=True,
                             description="Qwen3.5-2B that thinks less and answers better: models, data and eval outputs")
for kind, name, _ in repos:
    api.add_collection_item(coll.slug, item_id=f"{USER}/{name}", item_type=kind, exists_ok=True)
print("collection:", f"https://huggingface.co/collections/{coll.slug}")
for kind, name, _ in repos:
    print(("https://huggingface.co/" if kind == "model" else "https://huggingface.co/datasets/") + f"{USER}/{name}")
