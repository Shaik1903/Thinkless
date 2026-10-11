"""All charts for the README / Hugging Face model card. Each chart is skipped if its input doesn't exist yet.

results/charts/
  accuracy_vs_tokens_<bench>.png   one point per model: the headline trade-off
  accuracy_vs_budget_<bench>.png   accuracy if generation is cut at 2k..32k tokens (base vs ThinkLess)
  token_hist_<bench>.png           distribution of answer lengths (base vs ThinkLess)
  accuracy_bars.png                accuracy with 95% CI per benchmark and model
  truncation_bars.png              share of answers that hit the token cap (thinking loops)
  grpo_train_curves.png            GRPO reward and mean answer length per step (from trainer_state.json)
  sft_loss.png                     SFT training loss per step
  grpo_val_curve.png               validation accuracy vs tokens per GRPO checkpoint
  serving_throughput.png / serving_latency.png   from bench.jsonl
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

R = Path("results")
OUT = R / "charts"
RUNS = {"Base (thinking off)": "base_nothink", "Base (thinking on)": "base_think", "ThinkLess-SFT": "sft",
        "ThinkLess-GRPO": "grpo", "ThinkLess-GRPO-AWQ": "grpo_awq"}
BENCHES = ["gsm8k", "math500", "hmmt25", "gpqa"]
BASE, NEW = "Base (thinking on)", "ThinkLess-GRPO"


def metrics():
    return {name: json.load(open(R / f"{stem}.metrics.json")) for name, stem in RUNS.items()
            if (R / f"{stem}.metrics.json").exists()}


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=160)
    plt.close(fig)
    print("wrote", OUT / name)


def accuracy_vs_tokens(ms):
    for b in BENCHES:
        pts = {n: m[b] for n, m in ms.items() if b in m}
        if len(pts) < 2:
            continue
        fig, ax = plt.subplots(figsize=(6.5, 4.2))
        for n, m in pts.items():
            lo, hi = m["accuracy_ci95"]
            ax.errorbar(m["mean_tokens"], m["accuracy"] * 100, yerr=[[(m["accuracy"] - lo) * 100], [(hi - m["accuracy"]) * 100]],
                        fmt="o", capsize=3)
            ax.annotate(n, (m["mean_tokens"], m["accuracy"] * 100), textcoords="offset points", xytext=(6, 4), fontsize=8)
        ax.set(xlabel="Mean completion tokens", ylabel="Accuracy (%)", title=f"{b}: accuracy vs tokens (95% CI)")
        save(fig, f"accuracy_vs_tokens_{b}.png")


def accuracy_vs_budget(ms):
    for b in BENCHES:
        fig, ax = plt.subplots(figsize=(6.5, 4.2))
        drawn = 0
        for n in (BASE, "ThinkLess-SFT", NEW):
            if n in ms and b in ms[n]:
                ba = ms[n][b]["budget_accuracy"]
                ax.plot([int(k) for k in ba], [v * 100 for v in ba.values()], marker="o", label=n)
                drawn += 1
        if drawn < 2:
            plt.close(fig)
            continue
        ax.set(xscale="log", xlabel="Token budget (generation cut off here)", ylabel="Accuracy (%)",
               title=f"{b}: accuracy at a token budget")
        ax.legend()
        save(fig, f"accuracy_vs_budget_{b}.png")


def token_hist():
    for b in BENCHES:
        data = {}
        for n in (BASE, NEW):
            p = R / f"{RUNS[n]}.jsonl"
            if p.exists():
                data[n] = [r["n_tokens"] for r in map(json.loads, open(p)) if r["bench"] == b]
        if len(data) < 2 or not all(data.values()):
            continue
        fig, ax = plt.subplots(figsize=(6.5, 4.2))
        for n, xs in data.items():
            ax.hist(xs, bins=40, alpha=0.55, label=f"{n} (mean {sum(xs) / len(xs):,.0f})")
        ax.set(xlabel="Completion tokens", ylabel="Answers", title=f"{b}: how long the answers are")
        ax.legend()
        save(fig, f"token_hist_{b}.png")


def bars(ms, key, fname, ylabel, title):
    names = [n for n in RUNS if n in ms]
    if len(names) < 2:
        return
    fig, ax = plt.subplots(figsize=(8, 4.2))
    width = 0.8 / len(names)
    for i, n in enumerate(names):
        vals = [ms[n][b][key] * 100 if b in ms[n] else 0 for b in BENCHES]
        ax.bar([j + i * width for j in range(len(BENCHES))], vals, width, label=n)
    ax.set_xticks([j + width * (len(names) - 1) / 2 for j in range(len(BENCHES))], BENCHES)
    ax.set(ylabel=ylabel, title=title)
    ax.legend(fontsize=7)
    save(fig, fname)


def trainer_curves():
    p = R / "grpo_trainer_state.json"
    if p.exists():
        hist = [h for h in json.load(open(p))["log_history"] if "reward" in h]
        if hist:
            fig, ax1 = plt.subplots(figsize=(7, 4.2))
            steps = [h["step"] for h in hist]
            ax1.plot(steps, [h["reward"] for h in hist], color="tab:blue", alpha=0.8, label="mean reward")
            ax1.set(xlabel="GRPO step", ylabel="Mean reward", title="GRPO training: reward and answer length per step")
            ax2 = ax1.twinx()
            ax2.plot(steps, [h.get("completions/mean_length", 0) for h in hist], color="tab:orange", alpha=0.8,
                     label="mean completion length")
            ax2.set_ylabel("Mean completion tokens")
            fig.legend(loc="lower center", ncol=2, fontsize=8, bbox_to_anchor=(0.5, -0.02))
            fig.subplots_adjust(bottom=0.2)
            save(fig, "grpo_train_curves.png")
    p = R / "sft_trainer_state.json"
    if p.exists():
        hist = [h for h in json.load(open(p))["log_history"] if "loss" in h]
        if hist:
            fig, ax = plt.subplots(figsize=(6.5, 4.2))
            ax.plot([h["step"] for h in hist], [h["loss"] for h in hist], marker=".")
            ax.set(xlabel="SFT step", ylabel="Training loss", title="SFT on shortest-correct self-samples")
            save(fig, "sft_loss.png")


def val_curve():
    points = sorted((int(p.stem.split("-")[1].split(".")[0]), json.load(open(p))["mathval"])
                    for p in R.glob("val_checkpoint-*.metrics.json"))
    if not points:
        return
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.plot([m["mean_tokens"] for _, m in points], [m["accuracy"] * 100 for _, m in points], marker="o")
    for step, m in points:
        ax.annotate(str(step), (m["mean_tokens"], m["accuracy"] * 100), textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax.set(xlabel="Mean completion tokens", ylabel="Validation accuracy (%)", title="GRPO checkpoints (label = step)")
    save(fig, "grpo_val_curve.png")


def budget_forced():
    """Qwen thinking-budget eval: thinking cut at each budget and an answer forced (every question answered)."""
    runs = {"Base (thinking on)": "base", "ThinkLess-SFT": "sft", "ThinkLess (final)": "thinkless"}
    data = {n: json.load(open(R / f"bforce_{s}.metrics.json")) for n, s in runs.items()
            if (R / f"bforce_{s}.metrics.json").exists()}
    for bench in ("gsm8k", "math500"):
        fig, ax = plt.subplots(figsize=(6.5, 4.2))
        drawn = 0
        for n, m in data.items():
            pts = sorted((int(k.split("@")[1]), v["accuracy"] * 100) for k, v in m.items() if k.startswith(bench + "@"))
            if pts:
                ax.plot([b for b, _ in pts], [a for _, a in pts], marker="o", label=n)
                drawn += 1
        if not drawn:
            plt.close(fig)
            continue
        ax.set(xscale="log", xlabel="Thinking budget (tokens; answer forced when reached)", ylabel="Accuracy (%)",
               title=f"{bench}: accuracy with a forced thinking budget")
        ax.legend()
        save(fig, f"budget_forced_{bench}.png")


def serving():
    p = R / "bench.jsonl"
    if not p.exists():
        return
    rows = [json.loads(line) for line in open(p)]
    for key, fname, ylabel in (("tok_per_s", "serving_throughput.png", "Output tokens / s"),
                               ("p50_latency", "serving_latency.png", "Median end-to-end latency (s)")):
        fig, ax = plt.subplots(figsize=(8, 4.2))
        labels = list(dict.fromkeys(r["label"] for r in rows))
        concs = sorted({r["concurrency"] for r in rows})
        width = 0.8 / len(concs)
        for i, c in enumerate(concs):
            vals = [next((r[key] for r in rows if r["label"] == lab and r["concurrency"] == c), 0) for lab in labels]
            ax.bar([j + i * width for j in range(len(labels))], vals, width, label=f"concurrency {c}")
        ax.set_xticks([j + width * (len(concs) - 1) / 2 for j in range(len(labels))], labels, rotation=20, ha="right",
                      fontsize=8)
        ax.set(ylabel=ylabel, title=f"Serving on vLLM: {ylabel.lower()}")
        ax.legend()
        save(fig, fname)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    ms = metrics()
    accuracy_vs_tokens(ms)
    accuracy_vs_budget(ms)
    token_hist()
    bars(ms, "accuracy", "accuracy_bars.png", "Accuracy (%)", "Accuracy per benchmark")
    bars(ms, "truncation_rate", "truncation_bars.png", "Answers hitting the cap (%)", "Thinking loops: truncation rate")
    trainer_curves()
    val_curve()
    budget_forced()
    serving()
