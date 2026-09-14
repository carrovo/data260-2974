# Reproducible Run Instructions

## Requirements

- Python 3.11 or later
- Docker Desktop
- Ollama
- Local model: `qwen3:8b`

## Setup

```bash
git clone https://github.com/carrovo/data260-2974.git
cd data260-2974
git checkout hw2-final

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

ollama pull qwen3:8b
```

Make sure the Ollama application is running.

## Run the FastAPI Application

```bash
python -m uvicorn main:app \
  --app-dir code \
  --host 127.0.0.1 \
  --port 8274
```

Open the application at:

```text
http://localhost:8274
```

The listings endpoint can also be checked with:

```bash
curl http://localhost:8274/api/listings
```

## Run the LangGraph Demo

Open another Terminal, activate the virtual environment, and run:

```bash
source .venv/bin/activate

python code/hw2_graph_demo.py \
  --strict \
  --max-turns 4
```

## Reproduce the Experiments

```bash
mkdir -p tmp/hw02_reproduction
```

Schema-validation experiment:

```bash
python code/hw2_experiment_runner.py \
  --input reports/hw02/cases/schema_input.json \
  --experiment schema_validation \
  --runs 30 \
  --max-turns 10 \
  --output-stem schema_runs \
  --raw-dir tmp/hw02_reproduction
```

Turn-ceiling comparison:

```bash
python code/hw2_experiment_runner.py \
  --input reports/hw02/cases/schema_input.json \
  --experiment ceiling_2 \
  --runs 20 \
  --max-turns 2 \
  --output-stem ceiling_2_runs \
  --raw-dir tmp/hw02_reproduction

python code/hw2_experiment_runner.py \
  --input reports/hw02/cases/schema_input.json \
  --experiment ceiling_10 \
  --runs 20 \
  --max-turns 10 \
  --output-stem ceiling_10_runs \
  --raw-dir tmp/hw02_reproduction
```

Adversarial experiment:

```bash
python code/hw2_experiment_runner.py \
  --input reports/hw02/cases/adversarial_input.json \
  --experiment adversarial \
  --runs 5 \
  --max-turns 2 \
  --output-stem adversarial_runs \
  --raw-dir tmp/hw02_reproduction
```

## Run the Verification Script

```bash
python code/verify_hw2.py
```

The script writes its results to:

```text
reports/hw02/verification.json
```

Results may have small latency differences depending on the local hardware and model runtime.