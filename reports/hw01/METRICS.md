# Homework 1 Metrics

## Part 3: Non-Determinism Experiment

### Experiment Setup

- Model: `qwen3:8b`
- Fixed input file: `reports/hw01/cases/nondeterminism_input.json`
- Runs at temperature 0.0: 20
- Runs at temperature 0.7: 20
- Total successful runs: 40
- Model access: all calls passed through `src/model_client.py`

### Tag Results

| Metric | Temperature 0.0 | Temperature 0.7 |
|---|---:|---:|
| Number of runs | 20 | 20 |
| Distinct tag sets | 1 | 10 |
| Number of tags found in all 20 runs | 3 | 0 |
| Number of tags found in exactly one run | 0 | 11 |

### Tags Found in All 20 Runs

Temperature 0.0:

- Furnished Studio Apartment
- Near SJSU Campus
- Walkable Location

Temperature 0.7:

- None

### Tags Found in Exactly One Run

Temperature 0.0:

- None

Temperature 0.7:

- Furnished Studio Living
- SJSU Campus Proximity
- SJSU Proximity
- Walkable Campus
- Walking Distance Living
- sjsu campus nearby
- walkable studio
- walking distance from SJSU
- walking distance housing
- walking distance location
- walking distance to SJSU

### Latency Results

| Metric | Temperature 0.0 | Temperature 0.7 |
|---|---:|---:|
| p50 latency (ms) | 18078.26 | 27728.17 |
| p95 latency (ms) | 19686.47 | 31670.03 |
| p99 latency (ms) | 19889.03 | 32451.89 |

### Interpretation

At temperature 0.0, the same fixed input produced one identical tag set across all 20 runs. The three tags appeared in every run, demonstrating stable and repeatable output.

At temperature 0.7, the same input produced 10 distinct tag sets. No tag appeared in all 20 runs, and 11 tags appeared in exactly one run. This demonstrates that a higher temperature can produce different but related wording for identical input.

Temperature 0.7 also had higher p50, p95, and p99 latency than temperature 0.0 in this experiment.

Variation is acceptable for creative search tags and marketing descriptions. It is not acceptable for factual or legally important information such as rental prices, addresses, lease terms, or applicant eligibility.



## Part 4: Interactive Client Metrics

### Configuration

- Model: `qwen3:8b`
- Temperature: `0.0`
- Reasoning mode: disabled
- Total conversation turns: 5
- Agent instruction file: `AGENT.md`
- Raw token data: `reports/hw01/raw/token_counts.json`

### Per-Turn Token Usage

| Turn | Input Tokens | Output Tokens | Total Tokens | Cumulative Total | Bullet-Only Check |
|---:|---:|---:|---:|---:|:---:|
| 1 | 214 | 91 | 305 | 305 | PASS |
| 2 | 339 | 93 | 432 | 737 | PASS |
| 3 | 464 | 64 | 528 | 1265 | PASS |
| 4 | 567 | 81 | 648 | 1913 | PASS |
| 5 | 684 | 22 | 706 | 2619 | PASS |

### Statistics Checkpoints

| Checkpoint | Cumulative Input | Cumulative Output | Cumulative Total | Serialized History Length |
|---|---:|---:|---:|---:|
| After turn 3 | 1017 | 248 | 1265 | 1673 |
| After turn 5 | 2268 | 351 | 2619 | 2507 |

### Interpretation

The input-token count increased from 214 tokens in turn 1 to 684 tokens in turn 5 because the client sent the previous conversation history again with every new model request.

All five responses passed the bullet-only format check required by `AGENT.md`. However, passing the format check did not guarantee factual correctness. In turns 2 and 5, the model referred to code that was not present in the user's input. These results demonstrate that AI-generated code reviews must still be checked by a human.