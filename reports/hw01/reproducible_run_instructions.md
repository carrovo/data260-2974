# Homework 1 Reproducible Run Instructions

## Repository

GitHub repository:

https://github.com/carrovo/data260-2974

Run all commands from the repository root directory.

## Prerequisites

The following software is required:

- Git
- Docker Desktop
- Python 3.12
- Ollama
- Ollama model `qwen3:8b`

## 1. Clone the Repository

```bash
git clone https://github.com/carrovo/data260-2974.git
cd data260-2974
```

## 2. Create the Python Environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 3. Prepare the Local Model

Open the Ollama application and confirm that the service is running:

```bash
ollama --version
ollama pull qwen3:8b
ollama ls
```

The model list should contain `qwen3:8b`.

## 4. Build and Run the Web Application with Docker

Make sure Docker Desktop is running.

Build the image:

```bash
docker build -t data260-hw1 -f code/Dockerfile code
```

Run one container using the assigned port:

```bash
docker run -d -p 8274:80 --name data260-hw1-container data260-hw1
```

Confirm that the container is running:

```bash
docker ps --filter name=data260-hw1-container
```

Open the following address in a browser:

```text
http://localhost:8274
```

To stop the container after testing:

```bash
docker stop data260-hw1-container
```

## 5. Run the Planner-Reviewer-Finalizer Pipeline

Activate the virtual environment if it is not already active:

```bash
source .venv/bin/activate
```

Run the pipeline:

```bash
python code/agents_demo.py \
  --title "Studio Near SJSU" \
  --content "This furnished studio is located within walking distance of the SJSU campus." \
  --email "xuanhua.li@sjsu.edu" \
  --model "qwen3:8b" \
  --temperature 0.0 \
  --strict
```

The program should print Planner, Reviewer, Finalized, and Publish outputs as JSON.

All model requests are routed through:

```text
src/model_client.py
```

## 6. Run the Non-Determinism Experiment

The fixed experiment input is stored in:

```text
reports/hw01/cases/nondeterminism_input.json
```

Run 20 successful executions at temperature 0.0 and 20 at temperature 0.7:

```bash
python code/experiment_runner.py \
  --email "xuanhua.li@sjsu.edu" \
  --model "qwen3:8b" \
  --runs 20
```

The machine-readable results are written to:

```text
reports/hw01/raw/nondeterminism_runs.json
```

The command also prints distinct tag-set counts, tags shared by all runs, tags appearing once, and p50, p95, and p99 latency.

## 7. Run the Interactive Model Client

```bash
python code/hw1_client.py --model "qwen3:8b"
```

Use the following five prompts:

```text
Review only this exact Python code for correctness. Do not invent any code: def divide(a, b): return a / b
```

```text
Review only this exact Python code for correctness. Do not invent any code: def first_item(items): return items[0]
```

```text
Review only this exact Python code for security. Do not invent any code: password = "admin123"
```

After turn 3, enter:

```text
/stats
```

Continue with:

```text
Review only this exact Python code for maintainability. Do not invent any code: def calculate(x): return x * 0.0825
```

```text
Review only this exact Python code for correctness. Do not invent any code: def average(values): return sum(values) / len(values)
```

After turn 5, enter:

```text
/stats
```

Exit using:

```text
/exit
```

The recorded token results from the submitted run are stored in:

```text
reports/hw01/raw/token_counts.json
```

## 8. Expected Evidence Locations

- Run log: `reports/hw01/RUN_LOG.txt`
- Metrics: `reports/hw01/METRICS.md`
- AI-use disclosure: `reports/hw01/AI_USE.md`
- Raw experiment results: `reports/hw01/raw/nondeterminism_runs.json`
- Raw token results: `reports/hw01/raw/token_counts.json`
- Screenshots: `reports/hw01/screenshots/`
- Final report: `reports/hw01/report.pdf`
- Verification result: `reports/hw01/verification.json`