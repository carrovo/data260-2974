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

Status: `pending_real_model_comparison`
Model: `qwen3:8b`
Original-loop input: completed Part 2 real-model 21-run dataset
Reflexion configuration: maximum 2 retries, bounded tool/token/time budgets

| Metric | Original loop | Reflexion loop |
|---|---:|---:|
| Task success | pending | pending |
| Unsupported claims | pending | pending |
| Retry rate | pending | pending |
| Tool calls | pending | pending |
| Tokens | pending | pending |
| Latency (ms) | pending | pending |
| Verifier false rejections | pending | pending |

The `controlled_offline_reflection_case` validates failed → reflection →
success behavior but is excluded from this real-model comparison table.
<!-- PART3_METRICS_END -->
