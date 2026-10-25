# HW7 Part 3 — Mac Local Run Guide

Part 3 reuses the Part 2 fixed tasks, real Part 2 raw data, local
`qwen3:8b`, and the guarded temporary MySQL fixture. It does not connect to a
personal database and does not change JWT/RBAC, tool permissions, or safety
rules.

## Update the branch

From the repository root:

```zsh
git fetch origin
git switch hw7-work
git pull --ff-only origin hw7-work
source .venv/bin/activate
```

If the Python environment does not exist yet, follow `PART2_RUN.md` to create
`.venv`, install `requirements.txt`, install Ollama, and pull `qwen3:8b`.
The model download is approximately 5.2 GB and is performed only once.

## Controlled offline reflection screenshot

This mode needs neither Ollama nor MySQL. It is explicitly marked as a
scripted-model case and is never included in real comparison metrics:

```zsh
python code/hw7_part3_runner.py controlled-offline
```

It demonstrates an objectively failed first attempt, deterministic verifier
evidence, one concise reflection, and a successful second attempt.

## Start real services

In Terminal 1, keep Ollama running:

```zsh
ollama serve
```

In Terminal 2, from the repository root:

```zsh
source .venv/bin/activate
source reports/hw07/part3_local.sh
hw7_part3_start
```

The helper starts only the named temporary MySQL 8.4 container, recreates
`hw7_part2_fixture_2974`, verifies its fixed A/B/C seed data, and checks that
Ollama reports `qwen3:8b` installed. Keep both terminals open.

To repeat preflight without resetting the fixture:

```zsh
python code/hw7_part3_runner.py preflight
```

## Screenshot-friendly real Reflexion demos

Run each task separately:

```zsh
python code/hw7_part3_runner.py demo --task A
```

```zsh
python code/hw7_part3_runner.py demo --task B
```

```zsh
python code/hw7_part3_runner.py demo --task C
```

The terminal output shows tool calls, observations, verifier pass/fail,
unsupported-claim count, concise reflection when used, final answer, retry
count, total tool calls/tokens, and the external stop reason. It never prints
hidden chain-of-thought.

The external stop reason is always one of:

- `success`
- `budget_exhausted`
- `human_review`

## Real original-vs-Reflexion comparison

The committed Part 2 dataset already contains 21 real original-loop runs.
This command audits those runs with the enhanced verifier and runs 21 new
Reflexion cases—A, B, and C seven times each:

```zsh
python code/hw7_part3_runner.py comparison
```

Do not interrupt the command. Depending on retries and Mac model speed, it can
take approximately 15–60 minutes. It writes LF-terminated JSON/CSV data to:

- `reports/hw07/raw/part3_reflexion_runs.json`
- `reports/hw07/raw/part3_reflexion_runs.csv`
- `reports/hw07/raw/part3_comparison.json`
- `reports/hw07/raw/part3_comparison.csv`
- `reports/hw07/METRICS.md`

Before this real command succeeds, comparison files remain explicitly marked
`pending_real_model_comparison`; controlled offline numbers are excluded.

## Budgets and reflection isolation

Each task permits at most two Reflexion retries, for at most three attempts.
The default per-run budgets are 12 total tool calls, 24,000 total tokens, and
300 seconds. A reflection contains only a concise failure explanation,
verifier evidence, and revised strategy. It remains in the current run's user
context and cannot change system instructions, tools, schemas, safety gates,
JWT, or RBAC.

## Cleanup

After the demos and comparison:

```zsh
hw7_part3_stop
```

This removes the temporary fixture container and database. It does not stop
Ollama; stop `ollama serve` in Terminal 1 with `Ctrl-C` when finished.
