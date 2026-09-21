# HW3 Retrieval Experiment Results

## Setup

For this experiment, I compared three chunking methods:

- Token chunking
- Semantic chunking
- Sentence-window chunking

The corpus contains three PDF documents about California rental housing and fair housing rights. I prepared five evaluation questions before running the formal experiment. Each method returned the top five results for every question.

I used the `sentence-transformers/all-MiniLM-L6-v2` embedding model. Each embedding has 384 dimensions. The vector indexes were created in memory with LlamaIndex and `SimpleVectorStore`.

## Metrics

I used the following measurements:

- **Chunks:** Number of text chunks added to the index.
- **Average chunk length:** Average number of characters in each indexed chunk.
- **Top-1 cosine:** Highest cosine similarity among the top five results, averaged across the five questions.
- **Mean@5 cosine:** Average cosine similarity of the five returned results.
- **Recall@5:** Whether the expected source document appeared anywhere in the top five results.
- **Retrieval latency:** Average time needed to retrieve five results for one question.

For sentence-window chunking, the center sentence is embedded and used for retrieval ranking, while the returned context also includes nearby sentences. I calculated the reported cosine similarity using the expanded context. Because of this, the result with the highest expanded-context cosine is not always the first result ranked by the vector store.

## Overall Results

| Technique | Chunks | Average chunk length | Top-1 cosine | Mean@5 cosine | Recall@5 | Average latency |
|---|---:|---:|---:|---:|---:|---:|
| Semantic | 441 | 1124.10 | 0.737317 | 0.671641 | 1.00 | 9.39 ms |
| Sentence-window | 3797 | 130.56 | 0.723145 | 0.651483 | 1.00 | 36.61 ms |
| Token | 584 | 968.84 | 0.726728 | 0.686432 | 1.00 | 9.77 ms |

## Results by Question

| Technique | Question | Top-1 cosine | Mean@5 cosine | Recall@5 | Latency |
|---|---|---:|---:|---:|---:|
| Semantic | q1 | 0.723798 | 0.652585 | 1 | 9.03 ms |
| Semantic | q2 | 0.738375 | 0.698943 | 1 | 10.85 ms |
| Semantic | q3 | 0.752428 | 0.662899 | 1 | 9.01 ms |
| Semantic | q4 | 0.663607 | 0.603497 | 1 | 8.80 ms |
| Semantic | q5 | 0.808375 | 0.740281 | 1 | 9.27 ms |
| Sentence-window | q1 | 0.742179 | 0.650316 | 1 | 40.90 ms |
| Sentence-window | q2 | 0.705494 | 0.648584 | 1 | 34.30 ms |
| Sentence-window | q3 | 0.748160 | 0.685591 | 1 | 35.40 ms |
| Sentence-window | q4 | 0.667865 | 0.578528 | 1 | 35.95 ms |
| Sentence-window | q5 | 0.752029 | 0.694395 | 1 | 36.51 ms |
| Token | q1 | 0.726185 | 0.696028 | 1 | 10.13 ms |
| Token | q2 | 0.728498 | 0.703451 | 1 | 8.93 ms |
| Token | q3 | 0.727002 | 0.657718 | 1 | 9.78 ms |
| Token | q4 | 0.688493 | 0.633915 | 1 | 10.39 ms |
| Token | q5 | 0.763461 | 0.741050 | 1 | 9.63 ms |

## What I Found

### Token chunking

Token chunking produced 584 chunks. Its average retrieval time was 9.77 ms, and it had the highest Mean@5 cosine score at 0.686432.

This method was simple and performed consistently. One possible problem is that a fixed token boundary can separate sentences or split a legal explanation between two chunks.

### Semantic chunking

Semantic chunking produced 441 chunks, which was the smallest index. It had the highest average Top-1 cosine score at 0.737317 and the lowest average retrieval time at 9.39 ms.

The semantic chunks were longer because related sentences were grouped together. It took about 17.8 seconds to create these chunks, which was slower than the other chunking methods. However, once the index was built, retrieval was fast.

Based on these results, semantic chunking gave the best overall balance between index size, similarity, and query speed.

### Sentence-window chunking

Sentence-window chunking produced 3,797 indexed sentences. This was much more than the other two methods. Its average retrieval time was 36.61 ms, so it was also the slowest method.

This method returned useful surrounding context, but the larger number of indexed nodes increased the index size and retrieval time. Its average Top-1 cosine was 0.723145, which was close to the other methods but did not make up for the additional retrieval cost in this experiment.

The vector store ranked the center sentence, while my independent cosine calculation used the expanded sentence window. For this reason, the highest expanded-context cosine was not always attached to the first vector-store result.

## High-Scoring Result That Did Not Answer the Question

Question q5 asked how long a person has to file a housing discrimination complaint with HUD.

The first Semantic result had a cosine similarity of 0.808375. This was a high score, but the passage said that a person has two years to file a private civil lawsuit. That is a different legal action and does not answer the HUD complaint question.

The second result had a lower cosine similarity of 0.749331, but it contained the correct information: a person has one year after the alleged discrimination occurred or ended to file a complaint with HUD.

This result shows that cosine similarity measures how closely two pieces of text are related in meaning. It does not check whether the retrieved passage gives the correct answer. The first passage mentioned HUD, housing discrimination, filing, and a legal deadline, so it was very similar to the question even though it gave the wrong type of deadline.

It also shows a limitation of Recall@5. Recall@5 was 1.0 because the expected source document appeared in the results, but that alone does not mean the highest-scoring result answered the question correctly.

## Conclusion

All three methods reached a Recall@5 of 1.0, so the expected document appeared in the top five results for every question.

Semantic chunking performed best overall. It created the fewest chunks, had the highest average Top-1 cosine, and had the lowest average retrieval latency.

Token chunking was also competitive and had the highest Mean@5 cosine. It may be a good choice when simple and predictable chunk sizes are preferred.

Sentence-window chunking returned more surrounding context, but it created a much larger index and took longer to retrieve results. For this corpus, I would choose semantic chunking.

The false-positive example also shows why retrieval output should be checked by reading the passage. A high similarity score is useful, but it does not prove that a passage contains the correct answer.

## Generative AI Use and Verification

### 1. What did I use an AI assistant for?

I used an AI assistant to help me explain the LlamaIndex components, organize the experiment code, and troubleshoot errors.

I created and edited the files in Cursor, chose and checked the corpus documents, prepared the five questions, ran the commands in my local environment, reviewed the output, and saved the screenshots and result files.

### 2. What AI output was incorrect or needed verification?

The AI assistant incorrectly advised me to calculate Top-1 cosine using `cosine_values[0]`.

That calculation selected the cosine similarity of the first vector-store result. However, the assignment defines Top-1 cosine as the highest cosine similarity among the top-k results.

### 3. How did I detect the problem?

I checked the metric definition in the original HW3 instructions. The assignment states that Top-1 cosine should be the highest similarity among the top-k results for each technique.

The difference was visible in the sentence-window results because the vector store ranked the center sentence, while my independent cosine calculation used the expanded sentence window.

### 4. What did I change?

I restored the calculation to:

`max(cosine_values)`

I then reran the metrics script and regenerated the summary CSV, JSON, and per-query results.

After the correction, the average Sentence-window Top-1 cosine changed from 0.593357 to 0.723145. This value now follows the metric definition in the assignment.