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

## Quickstart (demo mode)

````bash
uv sync
MENDRIFT_DEMO=1 uv run mendrift-mcp     # stdio MCP server with fixture data
PYTHONPATH=src uv run pytest -v         # approval-gate test suite
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
- [ ] trajectory eval harness (~40 synthetic incidents, ungated-write hard fail)
- [ ] live mode: Evidently drift computation, MLflow registry via community mlflow-mcp
- [ ] publish: PyPI + MCP community servers registry
````
````

What this version contains vs the premature one: the **Agent design** section stays (routing, bounded loop, degradation — all true and running as of Phase 5, plus the real-model demo commands), the **Evaluation** section is removed entirely, the quickstart's pytest line says only "approval-gate test suite," and the status list has exactly five checked boxes with the eval harness back in the unchecked column.

