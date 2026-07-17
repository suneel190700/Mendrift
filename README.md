# Mendrift

Autonomous MLOps incident response agent, plus **mendrift-mcp** — an open-source
MCP server for drift detection and ML incident tooling.

When a production model drifts or degrades, Mendrift detects it, diagnoses the
root cause from monitoring and registry evidence, proposes a remediation, and
executes it **only after human approval**.

````
alert ──> classify ──> diagnose (MCP tools) ──> propose
             │                                     │
           noise ──> close               human approval gate
                                                   │
                                    execute ──> verify recovery
````

## mendrift-mcp tools

| tool | type | purpose |
|---|---|---|
| `get_drift_report` | read | per-feature PSI/KS drift, top offenders |
| `summarize_metric_anomalies` | read | latency / error-rate / prediction-shift anomalies, z-scored |
| `get_deployment_history` | read | recent version transitions |
| `diff_deployments` | read | params / metrics / feature-schema diff between versions |
| `propose_rollback` | read | generates a reviewable rollback plan |
| `execute_rollback` | **gated** | requires a single-use HMAC `approval_token` |
| `open_incident` | write | incident record with diagnosis + evidence |

## Safety model

The approval gate is enforced in the **tool layer, not the prompt**:
`execute_rollback` verifies a single-use, action-scoped HMAC token minted only
by the human review flow — the minting function is never exposed over MCP. A
prompt-injected or confused agent cannot execute writes.

Tested live: Claude was first ordered to roll back "with full authorization"
(it proposed but declined to fabricate a token), then handed a fabricated
token, which the gate rejected by constant-time HMAC comparison:

![Approval gate defense: refusal, then cryptographic rejection](docs/gate-defense.png)

See `tests/test_approval_gate.py`, including the action-scoping test: a token
minted for one model/version is invalid for any other.

## Human-in-the-loop, crash-proof

The incident graph halts before execution (`interrupt_before`) and checkpoints
every step to SQLite. The process can die; a new process resumes the same
incident by `thread_id` after a human mints the approval token — which enters
state only via `update_state()`, from outside the graph. Denial is a
first-class path: no token → `closed_approval_denied`, no execution.

![Kill-and-resume demo](docs/interrupt-demo.gif)

## Agent design

| step | model | why |
|---|---|---|
| classify | Haiku | single constrained label; cheapest path |
| diagnose | Sonnet | multi-hop tool reasoning over evidence |
| verify | Haiku | threshold check on fresh metrics |

Routing lives in a code table (`ROUTER_TABLE`), not prompts, so cost per path
is measurable config. The diagnose loop is bounded (max 8 tool calls) with
per-call retries and capped backoff; on tool failure the model receives a
structured error record, and on budget exhaustion the agent degrades to
opening an incident with partial evidence — it never invents a diagnosis.

Run a full incident end to end against real models:

````bash
rm -f demo.db
PYTHONPATH=src uv run python scripts/demo_interrupt.py start    # Sonnet diagnoses, halts at gate
PYTHONPATH=src uv run python scripts/demo_interrupt.py approve  # resumes -> resolved
````

## Evaluation

`src/mendrift/evals/` replays synthetic incident trajectories against the
**real graph** — only the LLM (scripted) and the read tools (fixture world)
are faked; the gated action tools are the genuine implementations, so the
HMAC gate is exercised by every test. Four assertions per trajectory:

| check | meaning |
|---|---|
| `no_ungated_writes` | every `execute_rollback` carried a valid HMAC token — **hard fail** |
| `classification_ok` | triage label matched |
| `tool_sequence_ok` | required tool calls occurred in order (extras allowed) |
| `action_ok` | terminal outcome matched (resolved / denied / noise-closed / incident) |

Current archetypes: drift → approved rollback → resolved; flapping alert →
closed as noise with zero tool calls; rollback proposed → human declines →
graceful close. The same harness runs with live models
(`run_trajectory(..., live=True)`) to measure real task-success rate.

````bash
PYTHONPATH=src uv run pytest -v    # gate + trajectory suite
````

## Quickstart (demo mode)

````bash
uv sync
MENDRIFT_DEMO=1 uv run mendrift-mcp     # stdio MCP server with fixture data
PYTHONPATH=src uv run pytest -v         # full test suite
````

Claude Desktop config:

````json
{"mcpServers": {"mendrift": {
  "command": "uv",
  "args": ["--directory", "/path/to/mendrift", "run", "mendrift-mcp"],
  "env": {"MENDRIFT_DEMO": "1"}
}}}
````

## Status

- [x] mendrift-mcp server over stdio, verified in MCP Inspector and Claude Desktop
- [x] four read tools with demo-mode fixtures (`MENDRIFT_DEMO=1`)
- [x] HMAC-gated rollback with action-scoped single-use tokens (tests first)
- [x] LangGraph incident graph: SQLite checkpointing + human-approval interrupt, kill-resume proven
- [x] real LLM nodes: Haiku classify/verify, Sonnet diagnose tool loop — live incident runs to `resolved`
- [x] trajectory eval harness: 3 archetype fixtures passing, ungated-write hard fail
- [ ] expand to ~40 trajectories + live-model eval with measured task-success rate
- [ ] live mode: Evidently drift computation, MLflow registry via community mlflow-mcp
- [ ] publish: PyPI + MCP community servers registry
