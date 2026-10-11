from bench import spec_counters

METRICS = """# HELP vllm:spec_decode_num_draft_tokens_total drafts
vllm:spec_decode_num_draft_tokens_total{engine="0",model_name="t"} 200.0
vllm:spec_decode_num_accepted_tokens_total{engine="0",model_name="t"} 150.0
vllm:num_requests_running{model_name="t"} 0.0
"""


def test_spec_counters_parse():
    assert spec_counters(METRICS) == (200.0, 150.0)
    assert spec_counters('vllm:num_requests_running{model_name="t"} 0.0\n') == (0.0, 0.0)
