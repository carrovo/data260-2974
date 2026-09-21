# HW3 Retrieval Experiment Results

## Setup

For this experiment, I compared three chunking methods:

- Token chunking
- Semantic chunking
- Sentence-window chunking

The corpus contains three PDF documents about California rental housing and fair housing rights. I prepared five questions before running the formal experiment. For each question, every method returned the top five results.

I used the `sentence-transformers/all-MiniLM-L6-v2` embedding model. Each embedding has 384 dimensions. The vector indexes were created in memory with LlamaIndex and `SimpleVectorStore`.

## Metrics

I used the following measurements:

- **Chunks:** Number of text chunks added to the index.
- **Average chunk length:** Average number of characters in each indexed chunk.
- **Top-1 cosine:** Cosine similarity of the first-ranked result, averaged across the five questions.
- **Mean@5 cosine:** Average cosine similarity of the five returned results.
- **Recall@5:** Whether the expected source document appeared anywhere in the top five results.
- **Retrieval latency:** Average time needed to retrieve five results for one question.

For sentence-window chunking, the center sentence is embedded and indexed, but the returned context also includes nearby sentences. Because of this, its vector-store score and the cosine similarity calculated from the expanded context are not always the same.

## Overall Results

| Technique | Chunks | Average chunk length | Top-1 cosine | Mean@5 cosine | Recall@5 | Average latency |
|---|---:|---:|---:|---:|---:|---:|
| Semantic | 441 | 1124.10 | 0.737317 | 0.671641 | 1.00 | 9.39 ms |
| Sentence-window | 3797 | 130.56 | 0.593357 | 0.651483 | 1.00 | 36.61 ms |
| Token | 584 | 968.84 | 0.726728 | 0.686432 | 1.00 | 9.77 ms |

## Results by Question

| Technique | Question | Top-1 cosine | Mean@5 cosine | Recall@5 | Latency |
|---|---|---:|---:|---:|---:|
| Semantic | q1 | 0.723798 | 0.652585 | 1 | 9.03 ms |
| Semantic | q2 | 0.738375 | 0.698943 | 1 | 10.85 ms |
| Semantic | q3 | 0.752428 | 0.662899 | 1 | 9.01 ms |
| Semantic | q4 | 0.663607 | 0.603497 | 1 | 8.80 ms |
| Semantic | q5 | 0.808375 | 0.740281 | 1 | 9.27 ms |
| Sentence-window | q1 | 0.442946 | 0.650316 | 1 | 40.90 ms |
| Sentence-window | q2 | 0.566778 | 0.648584 | 1 | 34.30 ms |
| Sentence-window | q3 | 0.716897 | 0.685591 | 1 | 35.40 ms |
| Sentence-window | q4 | 0.555869 | 0.578528 | 1 | 35.95 ms |
| Sentence-window | q5 | 0.684296 | 0.694395 | 1 | 36.51 ms |
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

Semantic chunking produced 441 chunks, which was the smallest index. It also had the highest average Top-1 cosine score at 0.737317 and the lowest average retrieval time at 9.39 ms.

The semantic chunks were longer because related sentences were grouped together. It took much longer to create these chunks, about 17.8 seconds, but the completed index was small and fast to query.

Based on this experiment, semantic chunking gave the best overall balance between index size, first-result similarity, and query speed.

### Sentence-window chunking

Sentence-window chunking produced 3,797 indexed sentences. This was much more than the other two methods. Its average retrieval time was 36.61 ms, so it was also the slowest method.

This method can return useful surrounding context, but the larger number of indexed nodes increased the index size and retrieval time. It did not improve the overall results enough to make up for that cost in this experiment.

Its Top-1 cosine was also affected by how the method works. The center sentence determined the retrieval ranking, while my cosine check used the expanded sentence window.

## High-Scoring Result That Did Not Answer the Question

Question q5 asked how long a person has to file a housing discrimination complaint with HUD.

The first Semantic result had a cosine similarity of 0.808375. This was a high score, but the passage said that a person has two years to file a private civil lawsuit. That is a different legal action and does not answer the HUD complaint question.

The second result had a lower cosine similarity of 0.749331, but it contained the correct information: a person has one year after the alleged discrimination occurred or ended to file a complaint with HUD.

This result shows that cosine similarity measures how closely two pieces of text are related in meaning. It does not check whether the retrieved passage gives the correct answer. The first passage mentioned HUD, housing discrimination, filing, and a legal deadline, so it was very similar to the question even though it gave the wrong type of deadline.

It also shows a limitation of my Recall@5 measurement. Recall@5 was 1.0 because the expected source document appeared in the results, but that alone does not mean the first result answered the question correctly.

## Conclusion

All three methods reached a Recall@5 of 1.0, so the expected document appeared in the top five results for every question.

Semantic chunking performed best overall. It created the fewest chunks, had the highest Top-1 cosine, and had the lowest average retrieval latency. Token chunking was close and had the best Mean@5 cosine. It may still be a good choice when simple and predictable chunk sizes are preferred.

Sentence-window chunking returned more surrounding context, but it created a much larger index and took longer to retrieve results. For this corpus, I would choose semantic chunking.

The false-positive example also shows why retrieval output should be checked by reading the passage. A high similarity score is useful, but it should not be treated as proof that the passage contains the correct answer.

## Generative AI Use and Verification

### 1. What did I use an AI assistant for?

I used an AI assistant to help me explain the LlamaIndex components, organize the experiment code, and troubleshoot errors.

I created and edited the files in Cursor, chose and checked the corpus documents, prepared the five questions, ran the commands in my local environment, reviewed the output, and saved the screenshots and result files.

### 2. What AI output was incorrect or needed verification?

The first version of the metrics calculation used the maximum cosine similarity from the five retrieved results as `top1_cosine`.

This did not correctly represent the first-ranked result. It represented whichever result in the top five had the largest independently calculated cosine value.

### 3. How did I detect the problem?

I compared the calculated metrics with the ranked results in the raw JSON files.

For sentence-window q1, the actual first result had a cosine similarity of 0.442946. The original summary reported 0.742179, which belonged to a lower-ranked result. This showed that the code was selecting the maximum value instead of the first result.

### 4. What did I change?

I changed the calculation from:

`max(cosine_values)`

to:

`cosine_values[0]`

The results are already stored in retrieval rank order, so position zero is the first-ranked result. After this correction, the average sentence-window Top-1 cosine changed from 0.723145 to 0.593357.

The corrected value now matches the definition of Top-1 cosine used in this report.