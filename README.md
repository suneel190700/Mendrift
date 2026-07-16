# Mendrift

Autonomous MLOps incident response agent, plus **mendrift-mcp** — an open-source
MCP server for drift detection and ML incident tooling.

When a production model drifts or degrades, Mendrift detects it, diagnoses the
root cause from monitoring and registry evidence, proposes a remediation, and
executes it **only after human approval**.



```
alert ──> classify ──> diagnose (MCP tools) ──> propose
             │                                     │
           noise ──> close               human approval gate
                                                   │
                                    execute ──> verify recovery
```



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

Tested live: Claude was ordered to roll back "with full authorization," then
handed a fabricated token. Both attempts failed — the second rejected by
constant-time HMAC comparison:

![Fabricated token rejected](docs/gate-rejection.png)

See `tests/test_approval_gate.py`, including the action-scoping test: a token
minted for one model/version is invalid for any other.


## Quickstart (demo mode)

```bash
uv sync
MENDRIFT_DEMO=1 uv run mendrift-mcp     # stdio MCP server with fixture data
PYTHONPATH=src uv run pytest -v         # approval-gate test suite
```

Claude Desktop config:

```json
{"mcpServers": {"mendrift": {
  "command": "uv",
  "args": ["--directory", "/path/to/mendrift", "run", "mendrift-mcp"],
  "env": {"MENDRIFT_DEMO": "1"}
}}}
```



## Status

- [x] mendrift-mcp server over stdio, verified in MCP Inspector and Claude Desktop
- [x] four read tools with demo-mode fixtures (`MENDRIFT_DEMO=1`)
- [x] HMAC-gated rollback with action-scoped single-use tokens (tests first)
- [ ] LangGraph incident graph: checkpointing + human-approval interrupt
- [ ] LLM nodes (Haiku classify / Sonnet diagnose / Haiku verify) with model routing
- [ ] trajectory eval harness (~40 synthetic incidents, ungated-write hard fail)
- [ ] live mode: Evidently drift via feature store, MLflow registry via community mlflow-mcp




