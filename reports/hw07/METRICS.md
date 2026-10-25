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
