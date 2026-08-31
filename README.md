# DATA 260 Homework 1

## Project Overview

This repository contains Homework 1 for DATA 260. The application is based on the assigned domain of rental housing listings.

The project includes:

- A rental-listing HTML form with JavaScript validation and JSON processing
- A Dockerized web application
- A local Planner-Reviewer-Finalizer agent pipeline using Ollama
- A non-determinism experiment comparing temperatures 0.0 and 0.7
- A reusable model adapter and an interactive code-review client
- Raw results, metrics, logs, screenshots, and verification evidence

## Personal Configuration

| Setting | Value |
|---|---:|
| SID4 | 2974 |
| PORT_BASE | 8274 |
| PREFIX | s2974 |
| SEED | 2974 |
| VERIFY_SEED | 262974 |
| DOMAIN_ID | 6 |
| Assigned domain | Rental housing listings |

Student: Xuanhua Li  
Hardware: Apple MacBook Air, M4, 16 GB memory  
Local model: `qwen3:8b`

## Repository Structure

```text
data260-2974/
├── code/
│   ├── web_application/
│   │   ├── index.html
│   │   └── feedback.js
│   ├── agents_demo.py
│   ├── experiment_runner.py
│   ├── hw1_client.py
│   ├── verify_hw1.py
│   └── Dockerfile
├── src/
│   └── model_client.py
├── reports/
│   ├── hw01/
│   │   ├── cases/
│   │   ├── raw/
│   │   ├── screenshots/
│   │   ├── RUN_LOG.txt
│   │   ├── METRICS.md
│   │   ├── AI_USE.md
│   │   ├── reproducible_run_instructions.md
│   │   └── verification.json
│   ├── hw02/
│   └── hw03/
├── AGENT.md
├── DOMAIN_SCHEMA.md
├── requirements.txt
└── README.md
```

Application code is kept in the shared `code/` and `src/` directories so that it can be extended in future homework assignments. Homework-specific evidence is stored under `reports/hw01/`.

## Local Web Application

Build the Docker image from the repository root:

```bash
docker build -t data260-hw1 -f code/Dockerfile code
```

Run the application on the assigned port:

```bash
docker run -d -p 8274:80 --name data260-hw1-container data260-hw1
```

Open:

```text
http://localhost:8274
```

## Python and Ollama Setup

Create and activate the Python environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Prepare the local model:

```bash
ollama pull qwen3:8b
ollama ls
```

## Agent Pipeline

Run the Planner-Reviewer-Finalizer pipeline:

```bash
python code/agents_demo.py \
  --title "Studio Near SJSU" \
  --content "This furnished studio is located within walking distance of the SJSU campus." \
  --email "xuanhua.li@sjsu.edu" \
  --model "qwen3:8b" \
  --temperature 0.0 \
  --strict
```

All application model calls pass through the reusable adapter at:

```text
src/model_client.py
```

## Non-Determinism Experiment

Run 20 executions at temperature 0.0 and 20 executions at temperature 0.7:

```bash
python code/experiment_runner.py \
  --email "xuanhua.li@sjsu.edu" \
  --model "qwen3:8b" \
  --runs 20
```

The raw results are saved to:

```text
reports/hw01/raw/nondeterminism_runs.json
```

## Interactive Model Client

Start the client:

```bash
python code/hw1_client.py --model "qwen3:8b"
```

Available commands:

- `/stats` displays the turn count, cumulative token counts, and serialized conversation-history length.
- `/exit` closes the client and displays final cumulative statistics.

## Part 4 Questions

### Why is prior conversation context resent with every turn?

A model request is stateless: the model does not automatically remember earlier API calls. To continue a conversation, the client sends the relevant previous user and assistant messages again with each new request. This allows the model to interpret the current message using earlier context.

### How is a system prompt different from a user message?

A system prompt defines the model's overall role, behavior, and response constraints. In this project, the contents of `AGENT.md` are sent as the system message and require bullet-only code reviews.

A user message contains the current task or question. It has a lower instructional role and should operate within the behavior established by the system prompt.

### Why do input tokens grow over a conversation?

Input tokens grow because each new request contains the system instructions, previous conversation history, and the newest user message. As additional turns are added to the history, more text must be serialized and sent to the model.

In the recorded run, the input-token count increased from 214 tokens in turn 1 to 684 tokens in turn 5.

### What eventually limits that growth?

The model's context window limits how many tokens can be processed in one request. Once the combined system prompt, conversation history, and current message approach that limit, the application must remove older messages, summarize earlier context, retrieve only relevant history, or use a model with a larger context window.

Longer context also increases latency and resource usage, so practical limits may be reached before the maximum context-window size.

## Verification

Run the self-check while the Docker application is available at `localhost:8274`:

```bash
python code/verify_hw1.py
```

The result is saved to:

```text
reports/hw01/verification.json
```

The submitted verification checks required files, experiment counts, token accounting, adapter usage, agent instructions, and the local Docker web application.

## Evidence and Documentation

- Detailed reproduction steps: `reports/hw01/reproducible_run_instructions.md`
- Run log: `reports/hw01/RUN_LOG.txt`
- Metrics: `reports/hw01/METRICS.md`
- AI-use disclosure: `reports/hw01/AI_USE.md`
- Raw data: `reports/hw01/raw/`
- Screenshots: `reports/hw01/screenshots/`
- Final report: `reports/hw01/report.pdf`

## Repository Link

https://github.com/carrovo/data260-2974