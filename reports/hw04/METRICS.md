# HW4 Metrics

## 1. Part 3 — Database Scale and N+1 Performance

### 1.1 Seeded database size

The database was reset and seeded with deterministic data using:

```text
SEED=2974
```

| Database item | Count |
|---|---:|
| Rental listings | 5,000 |
| Listing events | 200 |
| Distinct listings with events | 199 |

The seed output was:

```text
Listings created: 5000
Events created: 200
```

The raw database seed and verification were performed against:

```text
Database: s2974_rel
Domain: Rental housing listings
```

### 1.2 N+1 experiment design

The experiment compared two endpoint implementations:

- `naive`: loads related events separately for each listing
- `fixed`: uses eager loading with `selectinload`

The experiment used three page sizes:

```text
10, 50, 200
```

Each configuration was repeated 30 times:

```text
2 endpoint modes × 3 page sizes × 30 repetitions = 180 requests
```

The raw request count was verified as:

```text
181 CSV lines
```

This includes one CSV header and 180 request records.

### 1.3 N+1 latency results

All latency values are in milliseconds.

| Mode | Page size | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| naive | 10 | 4.297 | 6.749 | 12.849 |
| naive | 50 | 10.195 | 14.038 | 16.079 |
| naive | 200 | 32.827 | 39.263 | 61.212 |
| fixed | 10 | 1.863 | 2.286 | 2.968 |
| fixed | 50 | 3.335 | 3.751 | 3.947 |
| fixed | 200 | 9.815 | 10.889 | 17.264 |

Based on p50 latency, the fixed implementation was approximately:

| Page size | Approximate improvement |
|---:|---:|
| 10 | 2.3× faster |
| 50 | 3.1× faster |
| 200 | 3.3× faster |

The fixed implementation was faster for every tested page size. The difference became more visible as the page size increased because the naive implementation performs additional related-record work for each returned listing. The eager-loading implementation retrieves the related events more efficiently.

### 1.4 Index verification

The relationship column `listing_events.listing_id` uses a BTREE index.

The MySQL `EXPLAIN` output reported:

```text
Index lookup on e using listing_id
```

The index metadata showed:

```text
Key_name: listing_id
Column_name: listing_id
Index_type: BTREE
```

This confirms that MySQL uses the `listing_id` index for the join between `listings` and `listing_events`.

### 1.5 Part 3 raw files

```text
reports/hw04/raw/n_plus_one_requests.csv
reports/hw04/raw/n_plus_one_summary.json
```

---

## 2. Part 4 — RAG Experiment

### 2.1 Corpus

The RAG corpus contained five rental-housing PDF documents:

```text
corpus/hw03/ca_fair_housing_rights_booklet.pdf
corpus/hw03/ca_landlord_tenant_guide_2026.pdf
corpus/hw03/hud_fair_housing_booklet.pdf
corpus/hw04/hud_assistance_animal_notice.pdf
corpus/hw04/hud_fair_housing_guide_2025.pdf
```

The five documents were loaded successfully.

The experiment loaded:

```text
PDF pages: 239
```

### 2.2 Models and configurations

Embedding model:

```text
sentence-transformers/all-MiniLM-L6-v2
```

Local language model:

```text
qwen3:8b
```

The experiment compared three retrieval configurations:

| Configuration | Chunking technique |
|---|---|
| A | Token chunks |
| B | Semantic chunks |
| C | Sentence-window chunks |

Each configuration was tested with:

```text
k = 1, 3, 5
```

The evaluation set contained six questions:

- Q1–Q4: in-domain rental-housing questions
- Q5–Q6: out-of-domain refusal questions

The total number of RAG runs was:

```text
3 configurations × 3 k values × 6 questions = 54 runs
```

The run summary verified:

```text
Total runs: 54
In-domain runs: 36
Out-of-domain runs: 18
Refusal detections: 18
```

### 2.3 Chunking results

| Configuration | Technique | Chunks | Chunking latency (ms) | Indexing latency (ms) |
|---|---|---:|---:|---:|
| A | Token | 776 | 492.931 | 7,826.035 |
| B | Semantic | 548 | 26,472.662 | 5,749.356 |
| C | Sentence window | 4,655 | 248.802 | 17,445.369 |

The sentence-window configuration created the largest number of chunks because it creates overlapping context windows. The semantic configuration required more time during chunk creation because it uses embeddings to determine semantic boundaries.

### 2.4 RAG evaluation definitions

The following metrics were used:

- `answer_term_accuracy`: whether the generated answer contained the required concepts for Q1–Q4
- `source_recall_at_k`: whether the expected source document appeared in the retrieved context
- `refusal_rate`: whether Q5 and Q6 were correctly refused
- `overall_pass_rate`: whether the applicable answer, source, or refusal checks passed

The answer-term metric is a lightweight reproducible keyword-based evaluation. It is not intended to replace detailed human review of legal accuracy.

### 2.5 RAG evaluation results

| Configuration | k | Answer term accuracy | Source recall@k | Refusal rate | Overall pass rate |
|---|---:|---:|---:|---:|---:|
| A token | 1 | 1.00 | 0.50 | 1.00 | 0.6667 |
| A token | 3 | 1.00 | 0.75 | 1.00 | 0.8333 |
| A token | 5 | 1.00 | 1.00 | 1.00 | 1.0000 |
| B semantic | 1 | 1.00 | 0.50 | 1.00 | 0.6667 |
| B semantic | 3 | 1.00 | 0.75 | 1.00 | 0.8333 |
| B semantic | 5 | 0.75 | 1.00 | 1.00 | 0.8333 |
| C sentence window | 1 | 0.75 | 0.50 | 1.00 | 0.5000 |
| C sentence window | 3 | 1.00 | 0.75 | 1.00 | 0.8333 |
| C sentence window | 5 | 1.00 | 1.00 | 1.00 | 1.0000 |

### 2.6 RAG latency results

All values are mean milliseconds.

| Configuration | k | Mean retrieval latency | Mean LLM latency |
|---|---:|---:|---:|
| A token | 1 | 67.182 | 5,583.834 |
| A token | 3 | 43.480 | 5,753.765 |
| A token | 5 | 57.576 | 6,922.214 |
| B semantic | 1 | 51.611 | 5,072.011 |
| B semantic | 3 | 94.458 | 8,737.272 |
| B semantic | 5 | 78.523 | 28,569.861 |
| C sentence window | 1 | 117.747 | 6,611.094 |
| C sentence window | 3 | 215.335 | 9,233.385 |
| C sentence window | 5 | 140.583 | 9,850.385 |

### 2.7 RAG interpretation

Increasing `k` improved source recall for all three configurations. Source recall increased from 0.50 at `k=1` to 1.00 at `k=5`. This indicates that retrieving more context made it more likely that the expected source document was included.

Configuration A with `k=5` and Configuration C with `k=5` achieved the highest overall pass rate of 1.00.

Configuration B with `k=5` achieved perfect source recall, but its answer-term accuracy was 0.75. This means that one generated answer did not match the simple keyword rubric even though the expected source was retrieved. The difference may be caused by paraphrasing rather than a completely incorrect answer.

Configuration C with `k=1` had the lowest overall pass rate of 0.50. Its sentence-window representation created many chunks, and retrieving only one chunk sometimes failed to include the expected source or all of the necessary answer context.

The sentence-window configuration had the highest retrieval latency because it created 4,655 overlapping chunks. The semantic configuration also had a high LLM latency at `k=5`, indicating that the retrieved context and prompt were more expensive for the local model to process.

Q5 and Q6 were intentionally outside the rental-housing domain. All 18 out-of-domain runs were refused successfully, resulting in a refusal rate of 1.00. The domain guard prevented the application from answering unrelated questions.

### 2.8 Best configuration

The best overall result was achieved by:

```text
Configuration A: token chunking
k=5
Overall pass rate: 1.00
Source recall@k: 1.00
Answer term accuracy: 1.00
Refusal rate: 1.00
```

Configuration C with `k=5` also achieved an overall pass rate of 1.00, but it required more chunks and higher retrieval latency.

### 2.9 Part 4 raw files

```text
reports/hw04/raw/rag_outputs.jsonl
reports/hw04/raw/rag_outputs.csv
reports/hw04/raw/rag_run_summary.json
reports/hw04/raw/rag_per_run_metrics.jsonl
reports/hw04/raw/rag_metrics_summary.json
```
```