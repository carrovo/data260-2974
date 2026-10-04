# HW5 Metrics

## Part 3 Failure-Injection Experiment

Configuration:

- VERIFY_SEED: 262974
- Calls per failure rate: 50
- Total calls: 150
- Maximum attempts: 3
- Per-attempt timeout: 1.0 second
- Backoff delays: 10 ms and 20 ms
- Maximum backoff: 40 ms

| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) |
|---:|---:|---:|---:|
| 0% | 100.00% | 0.889 | 20.232 |
| 20% | 96.00% | 4.462 | 38.206 |
| 50% | 94.00% | 10.929 | 39.003 |

Based on this experiment, the retry settings seem reasonable for an interactive assistant. The p99 latency stayed below 40 ms at all three failure rates. Even with a 50% injected failure rate, 47 out of 50 calls still succeeded. The mean latency increased because some calls needed a second or third attempt.

One limitation is that the injected failures happened immediately. They did not wait for the full one-second timeout, so real database or network timeouts could make the slowest calls take much longer.

For batch processing, I would allow up to five attempts and use a longer timeout. I would also increase the backoff delays and add jitter. Since batch jobs do not need an immediate response, waiting longer would improve the chance of completion and help avoid many failed requests retrying at the same time.