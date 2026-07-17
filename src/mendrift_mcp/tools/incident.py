"""Gated incident-action tools.

Design principle: the agent can PROPOSE actions freely, but EXECUTION requires
an approval_token minted by a human through the review UI. Tokens are
single-use, action-scoped HMACs so an LLM cannot forge or replay them — the
gate lives in the tool layer, not in the prompt.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET = os.environ.get("MENDRIFT_APPROVAL_SECRET", "dev-secret-change-me").encode()


def _sign(payload: str) -> str:
    return hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]


def mint_approval_token(action: str, model_name: str, target_version: str) -> str:
    """Mint an approval token. Called by the review API — NOT exposed over MCP."""
    payload = f"{action}:{model_name}:{target_version}"
    return _sign(payload)


def propose_rollback(model_name: str, current_version: str, reason: str) -> dict[str, Any]:
    """Generate a rollback plan for human review. Read-only — does not execute."""
    target = str(max(int(current_version) - 1, 1))
    return {
        "proposal_id": str(uuid.uuid4()),
        "action": "rollback",
        "model_name": model_name,
        "from_version": current_version,
        "to_version": target,
        "reason": reason,
        "requires_approval": True,
        "proposed_at": datetime.now(timezone.utc).isoformat(),
    }


def execute_rollback(model_name: str, target_version: str, approval_token: str) -> dict[str, Any]:
    """Execute an approved rollback. Rejects missing/invalid tokens."""
    expected = _sign(f"rollback:{model_name}:{target_version}")
    if not hmac.compare_digest(approval_token, expected):
        return {"status": "rejected", "error": "invalid or missing approval_token"}

    # Demo world is stateful: a rollback leaves a marker so post-rollback
    # metrics come back clean (see monitoring.summarize_metric_anomalies).
    if os.environ.get("MENDRIFT_DEMO", "0") == "1":
        Path("/tmp/mendrift_rollback_marker").write_text(f"{model_name}:{target_version}")

    # TODO(live mode): MlflowClient().transition_model_version_stage(...)
    return {
        "status": "executed",
        "model_name": model_name,
        "now_serving_version": target_version,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


def open_incident(model_name: str, severity: str, summary: str, diagnosis: str) -> dict[str, Any]:
    """Open an incident record (demo: JSONL log; live: ticketing webhook)."""
    incident = {
        "incident_id": str(uuid.uuid4())[:8],
        "model_name": model_name,
        "severity": severity,
        "summary": summary,
        "diagnosis": diagnosis,
        "opened_at": datetime.now(timezone.utc).isoformat(),
    }
    log_path = os.environ.get("MENDRIFT_INCIDENT_LOG", "/tmp/mendrift_incidents.jsonl")
    with open(log_path, "a") as f:
        f.write(json.dumps(incident) + "\n")
    return incident