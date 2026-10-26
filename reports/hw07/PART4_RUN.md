# HW7 Part 4 Phase 2: ReAct bike membership advisor

The advisor uses `langgraph.prebuilt.create_react_agent(..., version="v2")`
from the pinned LangGraph dependencies. The graph receives three
`StructuredTool` wrappers around the strict Part 4 `csv_sql`,
`policy_retriever`, and `calculator` functions. The CSV path and committed
sanitized policy snapshot are injected by trusted server code; neither is a
model argument.

The same framework graph uses its supported `response_format` parameter with
the strict `Part4AdvisorResult` Pydantic schema. For that final node, the
metered wrapper delegates to the original provider's native
`ChatOllama.with_structured_output(Part4AdvisorResult,
method="json_schema", include_raw=True)` runnable. It does not emulate the
schema as an ordinary domain-tool call. LangGraph performs this one final
structured-response model call after the tool loop. The raw AIMessage usage
is counted exactly once in model-call and token metrics; its latency is
reported in `structured_response_latency_ms` and included in total latency.
The call stays inside the effective bounded wall-clock budget and is not a
tool call.

Immediately before that native call, the wrapper derives a compact final-field
grounding packet only from successful CSV, policy, and calculator timeline
events. The packet is strictly schema-validated, includes the exact weekly
rows and scalars, and reduces retrieved policy text to an exact citation set
that still proves all five pricing rules. It is appended only to the native
structured-output invocation. The provider must still emit the schema response;
the code does not substitute an answer, retry that call, or bypass the
independent verifier.

## Strict final-response compatibility

The preferred result is the provider's parsed Pydantic model; a parsed dict is
strictly revalidated with the same schema. Only when native parsing returns
`parsed=None` may the decoder inspect nonempty `raw.content`, accepting either
one plain JSON object or exactly one Markdown `json` code block containing one
JSON object. It never parses `additional_kwargs` or another provider-specific
object. All accepted forms must contain every required field and pass the same
independent cost/evidence verifier.

Prose surrounding JSON, multiple objects, malformed JSON, NaN/Infinity,
missing or extra fields, wrong types, and unsupported recommendation labels
are rejected. The code never computes or substitutes a missing model answer.
On an invalid result the CLI prints only safe diagnostics: response source,
content type, character count, and classification. It never prints the invalid
response text or hidden reasoning.
When native parsing reports an error, diagnostics may also include only its
exception type, never its message or raw response.

## Required tool progress guard

The runtime user instruction now states five ordered stages: exact sequential
`TOTAL_ROWS_SQL`, `TARGET_STATS_SQL`, and `WEEKLY_SQL` calls; retrieved policy
evidence sufficient for all five pricing rules; and calculator observations
supporting membership cost, pay-per-use cost, and savings. It explicitly says
that the next action starts with `TOTAL_ROWS_SQL` and that no final answer is
allowed before all stages are complete.

Progress is derived only from successful completed timeline events. Before a
required CSV call reaches LangGraph's `ToolNode`, the metered ReAct model
wrapper requires exactly one model-produced `csv_sql` call with the next exact
query. An altered, parallel, repeated, or out-of-order CSV proposal is not
executed. If the model instead attempts a final no-tool answer while a stage is
missing, the wrapper appends one concise `HumanMessage` naming only the next
missing stage and invokes the same tool-bound model again. The replacement
tool call must still originate from the model and is executed normally by the
unchanged LangGraph v2 graph; the wrapper never synthesizes a tool call or
calls a tool directly.

Because the fixed model uses temperature `0.0`, repeated repair invocations
must not receive identical input. Each bounded repair now carries its attempt
number and a safe classification of the prior mismatch. For a missing CSV
stage it also includes only that stage's exact SQL between explicit markers
and forbids parallel or additional tool calls. No rejected model content is
copied into the repair message or logs.

Stage 5 is tracked as three ordered successful observations: membership cost,
pay-per-use cost, and savings. If qwen attempts to finish between these
calculations, the correction names the next missing Stage 5 evidence item and
provides the exact grounded arithmetic expression between explicit markers.
The model must emit exactly one `calculator` call for that expression; the
unchanged LangGraph `ToolNode` still executes it. This prevents a deterministic
temperature-0 model from spending all repairs repeating the same calculation.

Each run permits at most three progress-repair model calls. Every repair is
included in model-call, token, latency, and wall-budget accounting but is not a
tool call. Exhaustion stops with `required_tool_progress_exhausted`. The
separate native JSON-schema structured-output node does not use this repair
path.

Verifier failures print only ordered completed tool names, counts by tool,
missing stage names, progress-repair count, model-call count, and elapsed time.
They do not print model content, reasoning, retrieved page text, SQL results,
credentials, or other sensitive values.

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
export HW7_PART4_WALL_BUDGET_SECONDS=300
```

Both values must be finite and positive; zero, negative, non-numeric, NaN,
and infinite values are rejected. The request timeout defaults to 60 seconds
and is capped by the effective wall budget. The wall budget defaults to 300
seconds and values above its hard maximum of 600 seconds are capped at 600.
The wall setting is read once per run and that same effective value controls
deadline checks, the framework Future, timeout messages, and reported metrics.

The earlier 120-second wall budget was empirically insufficient for the
sequential local qwen3:8b workflow: several ReAct model turns and tool calls
are followed by both a final ReAct turn and the native JSON-schema structured
output turn. The 300-second default remains a strict, finite budget; it does
not add a retry or fallback answer.

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
Python traceback. Wall-budget diagnostics contain only elapsed time, model and
completed-tool counts, the last completed tool name, and whether structured
output had started. A failed run does not overwrite pending, partial, or
already completed raw results and metrics.

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
recursion limit is 50, with at most 12 actual tool calls and a default
300-second wall time (hard maximum 600). The default bounded Ollama request
timeout is 60 seconds and cannot exceed the effective wall budget. Explicit stops
include `success`, `tool_call_budget_exhausted`,
`required_tool_progress_exhausted`, `wall_clock_budget_exhausted`,
`recursion_limit`, `malformed_tool_envelope`, `invalid_final_response`, and
`verification_failed`.

Cleanup only generated real-run output when desired:

```zsh
rm -f reports/hw07/raw/part4_agent_acceptance.json
```
