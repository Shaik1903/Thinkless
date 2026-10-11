"""Load test on real reasoning prompts with natural stopping (fixed-length benchmarks would hide token savings)."""
import argparse
import asyncio
import json
import re
import statistics
import time
import urllib.request

from openai import AsyncOpenAI
from transformers import AutoTokenizer

from data import build_prompt, load_eval


async def one(client, model, prompt, max_tokens):
    t0, first, n = time.perf_counter(), None, 0
    stream = await client.completions.create(
        model=model, prompt=prompt, max_tokens=max_tokens, temperature=1.0, top_p=0.95, stream=True,
        stream_options={"include_usage": True}, extra_body={"top_k": 20, "presence_penalty": 1.5})
    async for chunk in stream:
        if first is None and chunk.choices and chunk.choices[0].text:
            first = time.perf_counter()
        if chunk.usage:
            n = chunk.usage.completion_tokens
    end = time.perf_counter()
    return {"latency": end - t0, "ttft": (first or end) - t0, "tokens": n}


def spec_counters(metrics_text: str) -> tuple[float, float]:
    """(drafted, accepted) speculative tokens from vLLM's Prometheus text. Both 0 without spec decoding."""
    total = lambda name: sum(float(v) for v in re.findall(rf"^{name}(?:{{[^}}]*}})?\s+(\S+)$", metrics_text, re.M))
    return total("vllm:spec_decode_num_draft_tokens_total"), total("vllm:spec_decode_num_accepted_tokens_total")


def read_spec_counters(url):
    return spec_counters(urllib.request.urlopen(f"{url}/metrics").read().decode())


async def run(a):
    client = AsyncOpenAI(base_url=f"{a.url}/v1", api_key="unused")
    tok = AutoTokenizer.from_pretrained(a.tokenizer)
    prompts = [build_prompt(tok, p) for p in load_eval("math500")[:a.num]]
    sem = asyncio.Semaphore(a.concurrency)

    async def guarded(p):
        async with sem:
            return await one(client, a.model, p, a.max_tokens)

    drafts0, accepted0 = read_spec_counters(a.url)  # counters are cumulative per server: diff around this run
    t0 = time.perf_counter()
    res = await asyncio.gather(*(guarded(p) for p in prompts))
    wall = time.perf_counter() - t0
    drafts1, accepted1 = read_spec_counters(a.url)
    spec = {"spec_acceptance": (accepted1 - accepted0) / (drafts1 - drafts0)} if drafts1 > drafts0 else {}
    lat = [r["latency"] for r in res]
    out = {"label": a.label, "concurrency": a.concurrency, "requests": len(res),
           "req_per_s": len(res) / wall, "tok_per_s": sum(r["tokens"] for r in res) / wall,
           "mean_tokens": statistics.mean(r["tokens"] for r in res),
           "p50_latency": statistics.median(lat), "p95_latency": statistics.quantiles(lat, n=20)[18],
           "mean_ttft": statistics.mean(r["ttft"] for r in res), **spec}
    print(json.dumps(out))
    with open("results/bench.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--model", default="thinkless", help="served model name")
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--concurrency", type=int, required=True)
    ap.add_argument("--num", type=int, required=True)
    ap.add_argument("--max-tokens", type=int, default=8192)
    asyncio.run(run(ap.parse_args()))
