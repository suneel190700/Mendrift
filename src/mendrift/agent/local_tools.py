"""In-process tool layer: same contract the MCP layer will implement later.

    schemas() -> list[dict]      # Anthropic tool-schema format
    call(name, args) -> dict
"""
from __future__ import annotations

import os

os.environ.setdefault("MENDRIFT_DEMO", "1")

from mendrift_mcp.tools import incident, monitoring

SCHEMAS = [
    {"name": "get_drift_report",
     "description": "Per-feature data/prediction drift (PSI, KS) for a deployed model; overall flag and top drifted features.",
     "input_schema": {"type": "object", "properties": {"model_name": {"type": "string"}}, "required": ["model_name"]}},
    {"name": "summarize_metric_anomalies",
     "description": "Serving-metric anomalies (latency, error rate, prediction shift), z-scored, over a lookback window.",
     "input_schema": {"type": "object", "properties": {"model_name": {"type": "string"}}, "required": ["model_name"]}},
    {"name": "get_deployment_history",
     "description": "Recent deployments/version transitions for a model, newest first.",
     "input_schema": {"type": "object", "properties": {"model_name": {"type": "string"}}, "required": ["model_name"]}},
    {"name": "diff_deployments",
     "description": "Diff two model versions: params, eval metrics, feature schema. Primary root-cause tool after a deploy-correlated alert.",
     "input_schema": {"type": "object", "properties": {"model_name": {"type": "string"}, "version_a": {"type": "string"}, "version_b": {"type": "string"}}, "required": ["model_name", "version_a", "version_b"]}},
    {"name": "propose_rollback",
     "description": "Generate a rollback plan for human review. Read-only.",
     "input_schema": {"type": "object", "properties": {"model_name": {"type": "string"}, "current_version": {"type": "string"}, "reason": {"type": "string"}}, "required": ["model_name", "current_version", "reason"]}},
]

_DISPATCH = {
    "get_drift_report": monitoring.get_drift_report,
    "summarize_metric_anomalies": monitoring.summarize_metric_anomalies,
    "get_deployment_history": monitoring.get_deployment_history,
    "diff_deployments": monitoring.diff_deployments,
    "propose_rollback": incident.propose_rollback,
    "execute_rollback": incident.execute_rollback,
    "open_incident": incident.open_incident,
}


class LocalToolLayer:
    def schemas(self) -> list[dict]:
        return SCHEMAS

    def call(self, name: str, args: dict) -> dict:
        return _DISPATCH[name](**args)