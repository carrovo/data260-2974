# MongoDB and File-Based Memory Comparison

| Criterion | MongoDB-backed memory | AGENT.md / MEMORY.md memory |
|---|---|---|
| Inspectability | Requires MongoDB Compass, shell, or an API query. | Plain Markdown is immediately readable and editable. |
| Persistence after restart | Persists in the MongoDB volume after the API restarts. | Persists on disk and is versioned with Git. |
| Scalability across sessions | Strong: indexed collections support many users, sessions, messages, and episodic facts. | Limited: loading a growing Markdown file into every prompt becomes expensive and difficult to coordinate. |
| Facts that must not be forgotten | Structured storage is reliable, but similarity retrieval can miss a relevant fact. | Strong for a small set of critical facts because the file is always loaded into the prompt. |

The preferred design is hybrid: keep project rules and critical facts in the two Markdown files, while storing conversation history, summaries, embeddings, and per-user episodes in MongoDB.
