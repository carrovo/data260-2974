# HW7 Part 4 Phase 2: ReAct bike membership advisor

The advisor uses `langgraph.prebuilt.create_react_agent(..., version="v2")`
from the pinned LangGraph dependencies. The graph receives three
`StructuredTool` wrappers around the strict Part 4 `csv_sql`,
`policy_retriever`, and `calculator` functions. The CSV path and committed
sanitized policy snapshot are injected by trusted server code; neither is a
model argument.

## Mac prerequisites

- macOS zsh, Git, Python 3.12, Node/npm, and Ollama.
- The repository checked out on `hw7-work` with the committed Part 4 policy
  snapshot and both 600-row scenario CSVs.
- `qwen3:8b` downloaded locally (about 5.2 GB; Ollama's displayed size may
  vary by release).
- The existing Part 1 MySQL/JWT environment if running the React/FastAPI UI.
  The standalone Part 4 CLI does not connect to MySQL.

From the repository root:

```zsh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm --prefix frontend ci
ollama pull qwen3:8b
ollama serve
```

Keep `ollama serve` running in its own Terminal. Then run the non-model
preflight first:

```zsh
reports/hw07/part4_agent_mac.zsh preflight
```

The Ollama request timeout defaults to 60 seconds. It is configurable with the
non-secret `HW7_PART4_OLLAMA_TIMEOUT_SECONDS` environment variable when a
slower Mac needs a different bounded value:

```zsh
export HW7_PART4_OLLAMA_TIMEOUT_SECONDS=90
```

The value must be finite and positive. Values above 120 are capped at 120;
zero, negative, non-numeric, NaN, and infinite values are rejected. This does
not change the separate 120-second overall agent wall-clock budget.

Run the two real acceptance scenarios separately for readable screenshots:

```zsh
reports/hw07/part4_agent_mac.zsh membership_wins
reports/hw07/part4_agent_mac.zsh pay_per_use_wins
```

Separate acceptance commands merge by scenario, so the second run preserves
the first run and changes the pending metrics section to completed only after
both verified scenarios exist.

A controlled model request timeout exits nonzero and prints `TASK_SUCCESS:
false`, `STOP_REASON: wall_clock_budget_exhausted`, and a short error without a
Python traceback. A failed run does not overwrite pending, partial, or already
completed raw results and metrics.

The acceptance fixture's expected winner is passed only to the deterministic
post-run verifier. It is never included in model messages. Completed real-model
output is written to `reports/hw07/raw/part4_agent_acceptance.json`; until these
commands run it remains explicitly pending and no offline fake-model output is
substituted.

For an arbitrary eligible CSV:

```zsh
.venv/bin/python code/hw7_part4_runner.py analyze \
  --csv reports/hw07/data/part4/scenarios/membership_wins.csv \
  --url https://www.lyft.com/bikes/bay-wheels/pricing
```

To run the web UI, keep Ollama, MySQL, and the API/frontend processes running:

```zsh
export DATABASE_URL='mysql+pymysql://USER:PASSWORD@127.0.0.1/DATABASE'
export JWT_SECRET_KEY='use-a-local-random-value-of-at-least-32-characters'
.venv/bin/uvicorn main:app --app-dir code --host 127.0.0.1 --port 8274
npm --prefix frontend run dev
```

Open `http://localhost:5173`, sign in, and choose **Bike Membership Advisor**.
All authenticated roles may run this read-only analysis. Temporary uploads are
server-named and deleted in a `finally` block. The UI never shows a local path,
JWT, raw HTML, secret, or hidden reasoning.

## Fixed bounds and cleanup

The model configuration is `qwen3:8b`, temperature `0.0`, seed `2974`,
reasoning disabled, `num_ctx=4096`, and `num_predict=1024`. The framework
recursion limit is 50, with at most 12 actual tool calls and 120 seconds wall
time. The default bounded Ollama request timeout is 60 seconds. Explicit stops
include `success`, `tool_call_budget_exhausted`,
`wall_clock_budget_exhausted`, `recursion_limit`, `malformed_tool_envelope`,
`invalid_final_response`, and `verification_failed`.

Cleanup only generated real-run output when desired:

```zsh
rm -f reports/hw07/raw/part4_agent_acceptance.json
```
