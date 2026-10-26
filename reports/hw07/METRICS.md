# HW7 Metrics

<!-- PART2_METRICS_START -->
## Part 2 — Hand-written Agent Loop

Status: `completed_real_model_run`
Model: `qwen3:8b`
Configuration: `temperature=0.0`, `seed=2974`, `num_ctx=4096`, `num_predict=512`

| Metric | Result |
|---|---:|
| Call-level well-formed rate (all attempts) | 100.0% (49/49) |
| Call-level pre-repair rate | 100.0% |
| Call-level post-repair rate | N/A |
| Run-level completion rate | 100.0% (21/21) |

| Failure category | Count |
|---|---:|
| `malformed_arguments` | 0 |
| `unknown_tool` | 0 |
| `text_when_tool_required` | 0 |
| `lost_multi_step_chain` | 0 |
<!-- PART2_METRICS_END -->

<!-- PART3_METRICS_START -->
## Part 3 — Reflexion and Bounded Self-Correction

Status: `completed_real_model_comparison`

| Metric | Original loop | Reflexion loop |
|---|---:|---:|
| Task success (%) | 100.0% | 100.0% |
| Unsupported claims | 0 | 0 |
| Retry rate (%) | 0.0% | 0.0% |
| Average tool calls | 2.333 | 2.333 |
| Average tokens | 2037.333 | 2037.333 |
| Latency (ms) | 13001.236 | 12964.118 |
| Verifier false rejections | 0 | 0 |
<!-- PART3_METRICS_END -->

<!-- PART4_AGENT_METRICS_START -->
## Part 4 — Framework ReAct Bike Membership Advisor

Status: `pending_real_part4_agent_run`

Framework: `langgraph.prebuilt.create_react_agent(version="v2")`

Model configuration: `qwen3:8b`, temperature `0.0`, seed `2974`, reasoning
disabled, `num_ctx=4096`, `num_predict=1024`.

| Acceptance scenario | Recommendation | Tool calls | Tokens | Latency |
|---|---|---:|---:|---:|
| `membership_wins` | pending real Mac run | pending | pending | pending |
| `pay_per_use_wins` | pending real Mac run | pending | pending | pending |

The scripted-model tests exercise the actual LangGraph prebuilt graph but are
offline implementation tests only. Their outputs are not reported as real
`qwen3:8b` evidence.
<!-- PART4_AGENT_METRICS_END -->
