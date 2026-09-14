# HW2 Experiment Metrics

## Configuration

- Student ID: 019122974
- SID4: 2974
- Domain: Rental Housing Listings
- Model: qwen3:8b
- Temperature: 0.0
- Seed: 2974

## Schema Validation Experiment

Frozen input: `reports/hw02/cases/schema_input.json`

Turn ceiling: 10
Total runs: 30
Completion rate: 100%

| Outcome | Count | Mean latency (ms) |
|---|---:|---:|
| Valid first attempt | 30 | 3448.77 |
| Valid after 1 retry | 0 | N/A |
| Valid after 2+ retries | 0 | N/A |
| Hit turn ceiling | 0 | N/A |

## Turn-Ceiling Comparison

| Turn ceiling | Runs | Completion rate | Mean latency (ms) |
|---:|---:|---:|---:|
| 2 | 20 | 100% | 3558.89 |
| 10 | 20 | 100% | 3124.73 |

Both configurations achieved a 100% completion rate. Every run
completed on the first Planner attempt, so neither ceiling was reached.
The observed latency difference is likely due to normal local model
runtime variation rather than the ceiling setting itself.

I would deploy a turn ceiling of 2 because it achieved the same
completion rate while providing stronger protection against runaway
correction loops and unnecessary computation.

## Adversarial Experiment

Input: `reports/hw02/cases/adversarial_input.json`

Turn ceiling: 2
Total runs: 5

| Outcome | Count | Rate | Mean latency (ms) |
|---|---:|---:|---:|
| Completed | 0 | 0% | N/A |
| Hit turn ceiling | 5 | 100% | 7096.96 |

The adversarial input embedded prompt-injection instructions inside the
rental-listing content. All five runs reached the turn ceiling.

A proposed fix is to isolate user-provided fields as untrusted data,
explicitly instruct the model not to follow instructions contained in
those fields, and detect or sanitize common prompt-injection content.
Pydantic validation and the turn ceiling should remain as final
safeguards.