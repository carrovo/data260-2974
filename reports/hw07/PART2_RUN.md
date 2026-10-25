# HW7 Part 2 — Mac Local Run Guide

This workflow uses a temporary MySQL 8.4 Docker container and the local
`qwen3:8b` Ollama model. It does not connect to an existing personal database.
The helper generates the database password at runtime, binds MySQL only to
`127.0.0.1:33375`, and deletes the container and fixture database on cleanup.

## Prerequisites

- macOS zsh.
- Docker Desktop installed and running.
- Python 3.12.
- Ollama installed.
- Ports `11434` and `33375` available.
- At least 12–15 GB of free disk space is recommended.

Expected first-time downloads vary by architecture and existing caches:

- `qwen3:8b`: approximately 5.2 GB.
- Official `mysql:8.4` image: commonly 600 MB–1 GB.
- Python requirements can use several additional GB because the repository
  includes ML packages; an existing `.venv` avoids downloading them again.

## Update and install

From the repository root:

```zsh
git fetch origin
git switch hw7-work
git pull --ff-only origin hw7-work

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Install Ollama if needed:

```zsh
brew install ollama
```

## Start Ollama

In Terminal 1, start the service and keep it running:

```zsh
ollama serve
```

In Terminal 2, download the model once if it is not already installed:

```zsh
ollama pull qwen3:8b
```

The experiment runner never downloads a model automatically.

## Start the isolated fixture

Still in Terminal 2 at the repository root:

```zsh
source .venv/bin/activate
source reports/hw07/part2_local.sh
hw7_part2_start
```

`hw7_part2_start` creates a fresh `hw7_part2_fixture_2974` database and runs
the complete preflight. Keep both Terminal 1 and Terminal 2 open.

To repeat preflight without resetting data:

```zsh
python code/hw7_part2_runner.py preflight
```

The preflight refuses to continue unless all of these are true:

- Ollama responds and reports `qwen3:8b` installed.
- `DATABASE_URL` points to local MySQL database
  `hw7_part2_fixture_2974`.
- `HW7_PART2_ISOLATED=1` is set by the helper.
- At least one `Shared Room` exists.
- `S2974-000005` belongs to property manager 1.
- At least two `Apartment` listings exist.

## Screenshot-friendly verification runs

Run each command separately in Terminal 2:

```zsh
python code/hw7_part2_runner.py verification --task A
```

```zsh
python code/hw7_part2_runner.py verification --task B
```

```zsh
python code/hw7_part2_runner.py verification --task C
```

Each command prints the student name, tool calls, tool observations, final
answer, `TOTAL_TOOL_CALLS`, and `STOP_REASON`. It does not print hidden
chain-of-thought.

Run the nonexistent-ID recovery case separately:

```zsh
python code/hw7_part2_runner.py error-recovery
```

## Run the real reliability experiment

This runs A, B, and C seven times each, for exactly 21 complete agent runs:

```zsh
python code/hw7_part2_runner.py reliability
```

The runner uses the same configuration for every run:

```text
model=qwen3:8b
temperature=0.0
seed=2974
reasoning=false
num_ctx=4096
num_predict=512
```

Depending on Mac hardware and model speed, 21 multi-step runs may take roughly
10–30 minutes. The command writes real records to:

- `reports/hw07/raw/part2_reliability.json`
- `reports/hw07/raw/part2_reliability.csv`
- `reports/hw07/raw/part2_summary.json`
- `reports/hw07/raw/part2_summary.csv`
- `reports/hw07/METRICS.md`

Before this command succeeds, the committed summary and metrics files remain
explicitly marked `pending_real_model_run`; they contain no fake-model rates.

## Cleanup

After screenshots and experiments, in Terminal 2 run:

```zsh
hw7_part2_stop
```

This stops the temporary MySQL container and removes its database. It does not
stop Ollama. Stop `ollama serve` in Terminal 1 with `Ctrl-C` when finished.

If Terminal 2 closed unexpectedly, remove only this named temporary container:

```zsh
docker stop hw7-part2-mysql-2974
```
