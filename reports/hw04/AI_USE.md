# HW4 Generative AI Use Disclosure

## 1. What did I use an AI assistant for, and what did I do myself?

I used ChatGPT as a supplementary assistant for interpreting assignment
requirements, explaining error messages, reviewing code, and organizing the
documentation.

I completed and verified the implementation myself. This included configuring
MySQL, creating the SQLAlchemy models, implementing FastAPI authentication and
CRUD endpoints, building the React pages, running the application, creating the
seed data, executing the N+1 and RAG experiments, checking the raw results, and
capturing the required screenshots.

## 2. What AI-produced output was wrong or unsuitable?

An early AI-assisted plan incorrectly treated Part 4 as a comparison of three
chunking techniques: token, semantic, and sentence-window chunking. The actual
assignment required three system configurations: No RAG, Basic RAG, and
Context-engineered RAG.

## 3. How did I detect or verify the problem?

I reread the HW4 instructions and compared every requirement with the code and
generated output. The configuration names, refusal behavior, and evaluation
design did not match the assignment. I also verified the corrected system by
reviewing terminal output, raw JSON/CSV files, retrieved source information, and
the six-question results.

## 4. What did I change, and why does it work now?

I rewrote the RAG experiment to use `A_no_rag`, `B_basic_rag`, and
`C_context_engineered_rag`. I used 500-character chunks with 50-character
overlap, tested `k=1`, `k=3`, and `k=5`, added source labels and grounding
instructions, and required the exact refusal response for unsupported questions.

I reran all 54 configurations and regenerated the raw outputs and metrics. The
final results now compare the three required systems, record retrieval evidence,
evaluate citations and refusals, and show that the context-engineered
configuration correctly refuses Q5 and Q6.

## Tools and Models

- FastAPI and Uvicorn
- MySQL and SQLAlchemy
- React and Vite
- Ollama with `qwen3:8b`
- `sentence-transformers/all-MiniLM-L6-v2`
- ChatGPT

No passwords, API keys, or private credentials were committed to the repository.