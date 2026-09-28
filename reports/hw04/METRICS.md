# HW4 Metrics

## 1. Experiment Configuration

| Item | Value |
| --- | --- |
| SID4 | 2974 |
| Domain ID | 6 |
| Domain | Rental housing listings |
| Seed | 2974 |
| API port | 8274 |
| Database | `s2974_rel` |
| Local LLM | `qwen3:8b` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |

---

## 2. Database Scale

The MySQL database was reset and populated with deterministic data using seed 2974.

| Database item | Count |
| --- | ---: |
| Rental listings | 5,000 |
| Listing events | 200 |
| Distinct listings with events | 199 |

The seed script reported:

- `Listings created: 5000`
- `Events created: 200`

The database includes four primary tables:

- `users`
- `sessions`
- `listings`
- `listing_events`

The `sessions.user_id` column references `users.id`, and
`listing_events.listing_id` references `listings.id`. Both foreign keys use
`ON DELETE CASCADE`.

---

## 3. N+1 Query Experiment

### 3.1 Design

The experiment compared two authenticated listing endpoints:

| Mode | Implementation |
| --- | --- |
| Naive | Loads listings first and then lazily loads events for every listing |
| Fixed | Uses `selectinload` to retrieve related events in one additional query |

The tested page sizes were 10, 50, and 200. Each endpoint and page-size
combination was requested 30 times.

`2 modes × 3 page sizes × 30 repetitions = 180 requests`

The raw CSV contains 181 lines: one header and 180 request records.

### 3.2 Results

All latency values are milliseconds.

| Mode | Page size | SQL statements/request | p50 | p95 | p99 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Naive | 10 | 11 | 4.392 | 6.771 | 8.031 |
| Naive | 50 | 51 | 9.513 | 14.007 | 14.964 |
| Naive | 200 | 201 | 32.746 | 38.634 | 42.667 |
| Fixed | 10 | 2 | 1.837 | 2.558 | 2.688 |
| Fixed | 50 | 2 | 3.439 | 3.819 | 3.899 |
| Fixed | 200 | 2 | 9.832 | 11.372 | 17.637 |

### 3.3 Improvement

| Page size | Naive SQL | Fixed SQL | p50 speed-up |
| ---: | ---: | ---: | ---: |
| 10 | 11 | 2 | 2.39× |
| 50 | 51 | 2 | 2.77× |
| 200 | 201 | 2 | 3.33× |

The naive endpoint demonstrates the N+1 pattern directly. One query loads the
listings, followed by one event query for every listing. Its SQL count therefore
increases from 11 to 201 as the page size increases.

The fixed endpoint consistently executes two SQL statements: one for the
listings and one batched query for all related events. Its latency remained lower
at every tested page size, and the performance difference became larger at
page size 200.

### 3.4 Index Experiment

The additional index was created on:

`listing_events.event_type`

Index name:

`idx_listing_events_event_type`

Before adding the index, MySQL reported:

- Table scan on `listing_events`
- Estimated rows examined: 200
- Estimated cost: 20.2

After adding the BTREE index, MySQL reported:

- Index lookup using `idx_listing_events_event_type`
- Estimated rows examined: 50
- Estimated cost: 5.75

The index therefore changed the execution strategy from a full table scan to an
indexed lookup for filtering events by `event_type`.

### 3.5 Raw N+1 Files

- `reports/hw04/raw/n_plus_one_requests.csv`
- `reports/hw04/raw/n_plus_one_summary.json`

---

## 4. RAG Experiment

### 4.1 Corpus

The corpus contains five rental-housing PDF documents:

- `corpus/hw03/ca_fair_housing_rights_booklet.pdf`
- `corpus/hw03/ca_landlord_tenant_guide_2026.pdf`
- `corpus/hw03/hud_fair_housing_booklet.pdf`
- `corpus/hw04/hud_assistance_animal_notice.pdf`
- `corpus/hw04/hud_fair_housing_guide_2025.pdf`

A total of 239 readable PDF pages were loaded.

### 4.2 Chunking and Models

| Setting | Value |
| --- | --- |
| Chunk size | 500 |
| Chunk overlap | 50 |
| Chunks created | 430 |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Local language model | `qwen3:8b` |
| Seed | 2974 |
| Tested k values | 1, 3, 5 |

Every chunk stored its text, source filename, page number, and chunk ID.

### 4.3 Required Configurations

| Configuration | Description |
| --- | --- |
| `A_no_rag` | Sends the question directly to the local LLM |
| `B_basic_rag` | Sends raw retrieved chunks to the LLM |
| `C_context_engineered_rag` | Removes duplicate context, labels sources, requires citations, and refuses unsupported questions |

The exact refusal response was:

`I cannot answer this question from the provided documents.`

### 4.4 Evaluation Questions

The evaluation included six questions:

| Question | Type |
| --- | --- |
| Q1 | Answer contained in one chunk |
| Q2 | Answer requires two pieces of information |
| Q3 | Similar information across multiple documents |
| Q4 | Ambiguous but answerable question |
| Q5 | Answer not contained in the documents |
| Q6 | Unrelated to the rental-housing domain |

Q1–Q4 were answerable. Q5 and Q6 required refusal.

The full experiment contained:

`3 configurations × 3 k values × 6 questions = 54 runs`

### 4.5 Metric Definitions

- **Answer accuracy:** required answer concepts were present for Q1–Q4.
- **Retrieval accuracy:** the required source document or documents were retrieved.
- **Grounded rate:** the answer was correct, supported by retrieved material, and used the required source format.
- **Format compliance:** the response followed the applicable output format. Source citations were specifically required for Configuration C.
- **Refusal rate:** Q5 and Q6 used the required refusal response.
- **Overall pass rate:** all checks applicable to that question and configuration passed.

For Configurations A and B, format compliance was treated as satisfied because
those baselines did not require Configuration C’s structured citation format.

### 4.6 RAG Quality Results

| Configuration | k | Answer accuracy | Retrieval accuracy | Grounded rate | Format compliance | Refusal rate | Overall pass |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A No RAG | 1 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.0000 |
| A No RAG | 3 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.0000 |
| A No RAG | 5 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.0000 |
| B Basic RAG | 1 | 0.50 | 0.50 | 0.50 | 1.00 | 0.00 | 0.3333 |
| B Basic RAG | 3 | 0.75 | 0.75 | 0.50 | 1.00 | 0.00 | 0.3333 |
| B Basic RAG | 5 | 1.00 | 0.75 | 0.75 | 1.00 | 0.00 | 0.5000 |
| C Context-engineered RAG | 1 | 0.50 | 0.50 | 0.50 | 1.00 | 1.00 | 0.6667 |
| C Context-engineered RAG | 3 | 0.75 | 0.75 | 0.50 | 1.00 | 1.00 | 0.6667 |
| C Context-engineered RAG | 5 | 0.75 | 0.75 | 0.00 | 0.3333 | 1.00 | 0.3333 |

### 4.7 Latency Results

All values are mean milliseconds across the six questions.

| Configuration | k | Retrieval latency | LLM latency |
| --- | ---: | ---: | ---: |
| A No RAG | 1 | 0.000 | 10,721.509 |
| A No RAG | 3 | 0.000 | 9,694.885 |
| A No RAG | 5 | 0.000 | 9,819.483 |
| B Basic RAG | 1 | 102.294 | 7,527.127 |
| B Basic RAG | 3 | 63.152 | 13,225.052 |
| B Basic RAG | 5 | 82.587 | 50,504.844 |
| C Context-engineered RAG | 1 | 68.285 | 6,020.227 |
| C Context-engineered RAG | 3 | 64.072 | 8,222.513 |
| C Context-engineered RAG | 5 | 118.363 | 45,928.693 |

For Configuration C, unsupported questions were rejected by the deterministic
domain guard before calling the LLM. Their LLM latency was therefore zero, which
reduced Configuration C’s mean LLM latency.

### 4.8 Analysis

The experiment shows a clear difference between answering without retrieval,
basic retrieval, and context-engineered retrieval. Configuration A had no
retrieved evidence and achieved zero answer, retrieval, grounding, refusal, and
overall accuracy under the reproducible evaluation rubric. This baseline shows
that the local model alone was not dependable for these document-specific
questions.

Basic RAG improved as more chunks were retrieved. Its answer accuracy increased
from 0.50 at k=1 to 1.00 at k=5, while retrieval accuracy increased from 0.50 to
0.75. Its grounded rate reached 0.75 at k=5. However, Basic RAG did not reliably
refuse Q5 or Q6, so its refusal rate remained zero. It also produced the highest
mean LLM latency, 50.5 seconds at k=5. The additional context improved answer
coverage but increased prompt-processing cost.

Context-engineered RAG produced the strongest balanced behavior at k=1 and k=3.
Both settings achieved an overall pass rate of 0.6667 and a refusal rate of
1.00. The k=3 setting had higher answer and retrieval accuracy than k=1, reaching
0.75 for both, while maintaining full format compliance. It is therefore the
best overall configuration when answer quality, source retrieval, refusal
behavior, and latency are considered together.

Increasing k to 5 did not improve Configuration C. Although answer and retrieval
accuracy remained 0.75, the grounded rate fell to zero and format compliance
fell to 0.3333. Inspection of the generated answers showed that the larger
context sometimes caused the model to focus on related but incorrect sections.
For example, it answered a maximum-deposit question with information about uses
of security deposits and answered a return-deadline question with inspection
information. Some answerable k=5 responses also omitted the required final
source line. This is evidence that retrieving more chunks does not always
produce a better answer. Extra context can introduce distracting information
and increase generation latency.

The context-engineered refusal rule was the most robust safety improvement. All
Q5 and Q6 runs were refused with the required sentence at every tested k. The
experiment therefore supports using Configuration C with k=3 as the final
choice: it improved retrieval and answer accuracy over k=1, avoided the
context-overload behavior seen at k=5, preserved citation formatting, and
correctly refused unsupported and unrelated questions.

### 4.9 Raw RAG Files

- `reports/hw04/raw/rag_outputs.jsonl`
- `reports/hw04/raw/rag_outputs.csv`
- `reports/hw04/raw/rag_run_summary.json`
- `reports/hw04/raw/rag_retrieval_printouts.txt`
- `reports/hw04/raw/rag_per_run_metrics.jsonl`
- `reports/hw04/raw/rag_metrics_summary.json`