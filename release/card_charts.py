"""Model-card charts in a release-post style: bar panels with values on every bar, ThinkLess highlighted.

GSM8K, MATH-500 and GPQA only (no HMMT/AWQ). Reads release/run_results; writes
release/ThinkLess-2B/charts/*.png.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

R = Path(__file__).parent / "run_results"
OUT = Path(__file__).parent / "ThinkLess-2B" / "charts"
OUT.mkdir(parents=True, exist_ok=True)

FONT = next((f for f in ("Segoe UI", "Helvetica Neue", "Arial") if any(f == x.name for x in font_manager.fontManager.ttflist)),
            "DejaVu Sans")
INK, MUTED, GRID = "#111827", "#6B7280", "#E5E7EB"
plt.rcParams.update({
    "font.family": FONT, "font.size": 12, "text.color": INK, "axes.labelcolor": MUTED, "xtick.color": INK,
    "ytick.color": MUTED, "axes.edgecolor": GRID, "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": False, "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "figure.facecolor": "white", "savefig.facecolor": "white",
})
BENCH = {"gsm8k": "GSM8K", "math500": "MATH-500", "gpqa": "GPQA-Diamond"}
MODELS = {  # key: (label, color, highlighted)
    "base_think": ("Qwen3.5-2B", "#CBD5E1", False),
    "sft": ("ThinkLess-2B-SFT", "#93C5FD", False),
    "grpo": ("ThinkLess-2B", "#7C3AED", True),
    "grpo_fp8": ("ThinkLess-2B-FP8", "#C4B5FD", False),
}
M = {k: json.load(open(R / f"{k}.metrics.json")) for k in MODELS}


def bar_panel(ax, keys, values, fmt, top_pad):
    xs = range(len(keys))
    bars = ax.bar(xs, values, 0.72, color=[MODELS[k][1] for k in keys], zorder=2)
    for b, k, v in zip(bars, keys, values):  # offsets in points, so labels never collide with each other
        hl = MODELS[k][2]
        ax.annotate(fmt(v), (b.get_x() + b.get_width() / 2, v), xytext=(0, 5), textcoords="offset points",
                    ha="center", va="bottom", fontsize=13 if hl else 11.5, fontweight="bold" if hl else "normal",
                    color=INK if hl else MUTED)
    ax.set_xticks([])
    ax.tick_params(axis="y", length=0)


def legend(fig, keys, y):
    handles = [plt.Rectangle((0, 0), 1, 1, color=MODELS[k][1]) for k in keys]
    fig.legend(handles, [MODELS[k][0] for k in keys], loc="lower center", ncol=len(keys), frameon=False,
               fontsize=12, bbox_to_anchor=(0.5, y), handlelength=1.2, columnspacing=1.8)


# 1. Hero: accuracy (top) and tokens per answer (bottom) per benchmark
keys = list(MODELS)
fig, axes = plt.subplots(2, 3, figsize=(15, 8.6), gridspec_kw={"hspace": 0.38, "wspace": 0.18})
for j, (b, title) in enumerate(BENCH.items()):
    acc = [M[k][b]["accuracy"] * 100 for k in keys]
    ax = axes[0, j]
    bar_panel(ax, keys, acc, lambda v: f"{v:.1f}", 0.6)
    lo = min(acc)
    ax.set_ylim(max(0, lo - 12), max(acc) + 6)
    ax.set_title(title, fontsize=15, fontweight="bold", loc="left", pad=10)
    if j == 0:
        ax.set_ylabel("Accuracy (%)")
    tok = [M[k][b]["mean_tokens"] / 1000 for k in keys]
    ax = axes[1, j]
    bar_panel(ax, keys, tok, lambda v: f"{v:.1f}k", max(tok) * 0.02)
    ax.set_ylim(0, max(tok) * 1.32)
    base = tok[0]
    for i, (k, v) in enumerate(zip(keys, tok)):
        if k != "base_think":
            ax.annotate(f"-{1 - v / base:.0%}", (i, v), xytext=(0, 25), textcoords="offset points", ha="center",
                        va="bottom", fontsize=11.5, color="#059669", fontweight="bold")
    if j == 0:
        ax.set_ylabel("Tokens per answer")
fig.text(0.075, 0.965, "ThinkLess-2B: better answers, far less thinking", fontsize=20, fontweight="bold")
fig.text(0.075, 0.925, "Accuracy (top) and mean reasoning tokens per answer (bottom), 81,920-token budget",
         fontsize=12.5, color=MUTED)
legend(fig, keys, 0.0)
fig.subplots_adjust(top=0.84, bottom=0.09, left=0.07, right=0.98)
fig.savefig(OUT / "headline.png", dpi=160)
plt.close(fig)

# 2. Budget forcing: grouped bars per budget, values on bars
BF = {k: json.load(open(R / f"bforce_{k}.metrics.json")) for k in ("base", "sft", "thinkless")}
bkeys = {"base": "base_think", "sft": "sft", "thinkless": "grpo"}
budgets = [2048, 4096, 8192, 16384]
fig, axes = plt.subplots(1, 2, figsize=(15, 5.6), gridspec_kw={"wspace": 0.12})
w = 0.27
for ax, b in zip(axes, ("gsm8k", "math500")):
    allv = []
    for i, (bk, mk) in enumerate(bkeys.items()):
        vals = [BF[bk][f"{b}@{x}"]["accuracy"] * 100 for x in budgets]
        allv += vals
        xs = [j + (i - 1) * w for j in range(len(budgets))]
        ax.bar(xs, vals, w * 0.92, color=MODELS[mk][1], zorder=2)
        hl = MODELS[mk][2]
        for x, v in zip(xs, vals):
            ax.text(x, v + 0.8, f"{v:.0f}", ha="center", fontsize=11 if hl else 10,
                    fontweight="bold" if hl else "normal", color=INK if hl else MUTED)
    ax.set_xticks(range(len(budgets)), ["2k", "4k", "8k", "16k"], fontsize=12)
    ax.set_xlabel("Thinking budget (tokens)")
    ax.set_ylim(min(allv) - 12, max(allv) + 7)
    ax.set_title(BENCH[b], fontsize=15, fontweight="bold", loc="left", pad=10)
    ax.tick_params(axis="both", length=0)
axes[0].set_ylabel("Accuracy (%)")
fig.text(0.06, 0.95, "Accuracy under a hard thinking budget", fontsize=20, fontweight="bold")
fig.text(0.06, 0.895, "Thinking is stopped at the budget and the model must answer (Qwen's thinking-budget recipe)",
         fontsize=12.5, color=MUTED)
legend(fig, list(bkeys.values()), 0.0)
fig.subplots_adjust(top=0.78, bottom=0.2, left=0.06, right=0.98)
fig.savefig(OUT / "budget_forcing.png", dpi=160)
plt.close(fig)

# 3. Serving: latency per request (horizontal bars, sorted), speed-up vs base
rows = [json.loads(l) for l in open(R / "bench.jsonl")]
cfg = [("base", "Qwen3.5-2B", "#CBD5E1"), ("base-mtp", "Qwen3.5-2B + MTP", "#CBD5E1"),
       ("thinkless", "ThinkLess-2B", "#C4B5FD"), ("thinkless-fp8", "ThinkLess-2B-FP8", "#C4B5FD"),
       ("thinkless-fp8-mtp", "ThinkLess-2B-FP8 + MTP", "#A78BFA"), ("thinkless-mtp", "ThinkLess-2B + MTP", "#7C3AED")]
fig, axes = plt.subplots(1, 2, figsize=(15, 5.4), gridspec_kw={"wspace": 0.45})
for ax, c, title in zip(axes, (1, 16), ("1 request at a time", "16 concurrent requests")):
    lat = {lab: next(r["p50_latency"] for r in rows if r["label"] == lab and r["concurrency"] == c) for lab, _, _ in cfg}
    order = sorted(cfg, key=lambda t: -lat[t[0]])
    ys = range(len(order))
    ax.barh(ys, [lat[t[0]] for t in order], 0.66, color=[t[2] for t in order], zorder=2)
    base = lat["base"]
    for y, (lab, name, _) in zip(ys, order):
        v, hl = lat[lab], lab == "thinkless-mtp"
        tag = "" if lab == "base" else f"   {base / v:.1f}x faster"
        ax.text(v + base * 0.015, y, f"{v:.1f}s{tag}", va="center", fontsize=12 if hl else 11,
                fontweight="bold" if hl else "normal", color=INK if hl else MUTED)
    ax.set_yticks(ys, [t[1] for t in order], fontsize=11.5)
    ax.set_xlim(0, base * 1.45)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.set_xlabel("Median latency per request (s)")
    ax.set_title(title, fontsize=15, fontweight="bold", loc="left", pad=10)
    ax.tick_params(axis="both", length=0)
fig.text(0.02, 0.95, "Serving speed on vLLM (one H100)", fontsize=20, fontweight="bold")
fig.text(0.02, 0.895, "Fewer tokens per answer x faster tokens with MTP speculative decoding (max 8,192 output tokens)",
         fontsize=12.5, color=MUTED)
fig.subplots_adjust(top=0.8, bottom=0.12, left=0.15, right=0.98)
fig.savefig(OUT / "serving.png", dpi=160)
plt.close(fig)

for old in ("accuracy_vs_tokens.png", "tokens.png", "serving_latency.png"):
    (OUT / old).unlink(missing_ok=True)
print("font:", FONT, "| charts:", sorted(p.name for p in OUT.glob("*.png")))
