# HW6 Metrics

| Setting | Mean prompt tokens/turn | Mean latency (ms) | Probe quality (1-5) |
|---|---:|---:|---:|
| SHORT_TERM_N=4 | 936.800 | 12796.745 | 4.600 |
| SHORT_TERM_N=12 | 1044.200 | 15098.258 | 4.200 |
| SHORT_TERM_N=30 | 1249.033 | 19876.919 | 4.600 |
| Importance eviction (N=12) | 911.567 | 14989.820 | 4.600 |

## Eviction comparison

Prompt-token savings: 12.702%
Probe-quality change: 0.400

## Cost estimate

Best: Importance eviction (N=12) - $626.41
Worst: SHORT_TERM_N=30 - $751.19

Selection rule: Best is the lowest-cost setting within 0.5 points of the highest probe-quality score. Worst is the highest-cost measured setting.
