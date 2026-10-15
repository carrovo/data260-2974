# HW6 Reproduction Guide

## 1. Environment

From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull qwen3:8b
```

Keep the existing HW5 `.env` file containing `DATABASE_URL`. The HW6 MongoDB defaults are:

```text
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=s2974_doc
SHORT_TERM_N=12
SUMMARIZE_EVERY_USER_MSGS=4
EPISODIC_TOP_K=3
```

## 2. Services

Start MongoDB:

```bash
docker compose -f docker-compose.hw6.yml up -d
docker compose -f docker-compose.hw6.yml ps
```

Make sure the existing MySQL database and Ollama are running, then start FastAPI:

```bash
source .venv/bin/activate
uvicorn main:app --app-dir code --host 127.0.0.1 --port 8274
```

Open:

- Swagger: `http://127.0.0.1:8274/docs`
- HW6 chat page: `http://127.0.0.1:8274/hw6-chat`

## 3. Checks and experiments

In a second terminal:

```bash
source .venv/bin/activate
python code/test_hw6_offline.py
python code/hw6_memory_experiment.py
python code/verify_hw6.py
```

The full memory experiment performs 30 conversation turns and five probes under each of four settings. It can take a substantial amount of time with `qwen3:8b`. Do not interrupt it after it starts writing results.

## 4. Stop MongoDB after evidence is collected

```bash
docker compose -f docker-compose.hw6.yml down
```

Do not add `-v`; the named volume preserves the MongoDB evidence.
