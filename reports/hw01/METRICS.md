# Homework 1 Metrics

## Part 3: Non-Determinism Experiment

### Experiment Setup

- Model: `qwen3:8b`
- Fixed input file: `reports/hw01/cases/nondeterminism_input.json`
- Runs at temperature 0.0: 20
- Runs at temperature 0.7: 20
- Total successful runs: 40

## Tag Results

|                Metric                   |    Temperature 0.0 | Temperature 0.7 |
|             Number of runs              |         20         |        20       |
|            Distinct tag sets            |         1          |        13       |
|     Number of tags found in all 20 runs |         3          |        0        |
| Number of tags found in exactly one run |         0          |        10       |

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

- SJSU Campus Proximity
- SJSU Proximity
- Walkable Campus Area
- Walkable Living
- Walkable SJSU Studio
- Walking Distance Living
- student housing near sjsu
- student-friendly housing
- walking distance
- walking distance accommodation

## Latency Results

|     Metric       | Temperature 0.0 | Temperature 0.7 |
| p50 latency (ms) |     16602.57    |     24025.72    |
| p95 latency (ms) |     17982.47    |     28342.23    |
| p99 latency (ms) |     18089.38    |     29895.57    |

## Interpretation

At temperature 0.0, the same input produced the same three tags in all 20 runs. This setting produced stable and repeatable results.

At temperature 0.7, the same input produced 13 different tag sets. No tag appeared in all 20 runs. This means that two users submitting identical input may receive different but related tags.

In this experiment, temperature 0.7 also had higher latency than temperature 0.0.

Variation is acceptable when the model generates creative search tags or marketing descriptions for a rental listing.

Variation is not acceptable when the model produces factual or legally important information, such as the rental price, property address, lease terms, or applicant eligibility.