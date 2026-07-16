"""Read-only diagnostic tools: drift reports, anomaly summaries, deployment history.

Backed by Evidently for drift computation and a pluggable DeploymentStore.
In demo mode (MENDRIFT_DEMO=1) tools serve from seeded fixture data so the
server is demoable without live infrastructure.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[3] / "mendrift" / "evals" / "trajectories"


def _demo_mode() -> bool:
    return os.environ.get("MENDRIFT_DEMO", "0") == "1"


def _load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def get_drift_report(
    model_name: str,
    reference_window_hours: int = 168,
    current_window_hours: int = 24,
) -> dict[str, Any]:
    """Compute a data/prediction drift report for a deployed model.

    Compares the current serving window against a reference window using
    Evidently (PSI + KS tests per feature). Returns per-feature drift scores,
    overall drift flag, and the top drifted features.

    Args:
        model_name: Registered model name as it appears in the model registry.
        reference_window_hours: Reference window size (default 7 days).
        current_window_hours: Current window size (default 24 hours).
    """
    if _demo_mode():
        return _load_fixture("drift_report_demo") or {
            "model_name": model_name,
            "overall_drift": True,
            "n_features": 42,
            "n_drifted": 6,
            "top_drifted_features": [
                {"feature": "txn_amount_zscore", "psi": 0.31, "test": "PSI"},
                {"feature": "merchant_category_freq", "psi": 0.27, "test": "PSI"},
                {"feature": "hour_of_day", "ks_pvalue": 0.001, "test": "KS"},
            ],
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
    # TODO(live mode): pull reference/current frames from the feature store,
    # run evidently Report(metrics=[DataDriftPreset()]) and serialize.
    raise NotImplementedError("Live mode requires feature-store wiring; set MENDRIFT_DEMO=1")


def summarize_metric_anomalies(
    model_name: str,
    lookback_hours: int = 24,
) -> dict[str, Any]:
    """Summarize serving-metric anomalies (latency, error rate, prediction stats).

    Returns metric series statistics with anomaly windows flagged via rolling
    z-score, suitable for an LLM to reason over without raw time series.
    """
    if _demo_mode():
        return _load_fixture("metric_anomalies_demo") or {
            "model_name": model_name,
            "lookback_hours": lookback_hours,
            "anomalies": [
                {
                    "metric": "p95_latency_ms",
                    "baseline": 180,
                    "current": 460,
                    "zscore": 4.2,
                    "window_start": "2026-07-12T09:00:00Z",
                },
                {
                    "metric": "prediction_positive_rate",
                    "baseline": 0.031,
                    "current": 0.058,
                    "zscore": 3.1,
                    "window_start": "2026-07-12T08:30:00Z",
                },
            ],
        }
    raise NotImplementedError("Live mode requires metrics backend; set MENDRIFT_DEMO=1")


def get_deployment_history(model_name: str, limit: int = 10) -> dict[str, Any]:
    """List recent deployments/version transitions for a model, newest first."""
    if _demo_mode():
        return _load_fixture("deployment_history_demo") or {
            "model_name": model_name,
            "deployments": [
                {"version": "14", "stage": "Production", "deployed_at": "2026-07-12T08:05:00Z", "run_id": "run_f83a"},
                {"version": "13", "stage": "Archived", "deployed_at": "2026-07-02T14:11:00Z", "run_id": "run_c19d"},
            ][:limit],
        }
    raise NotImplementedError("Live mode requires registry wiring; set MENDRIFT_DEMO=1")


def diff_deployments(model_name: str, version_a: str, version_b: str) -> dict[str, Any]:
    """Diff two model versions: training data span, params, eval metrics, feature schema.

    The primary root-cause tool: correlates 'what changed' between the incumbent
    and the newly deployed version.
    """
    if _demo_mode():
        return _load_fixture("deployment_diff_demo") or {
            "model_name": model_name,
            "version_a": version_a,
            "version_b": version_b,
            "param_diffs": {"max_depth": ["6", "9"], "training_data_end": ["2026-06-20", "2026-07-10"]},
            "metric_diffs": {"val_auc": [0.912, 0.905], "val_recall": [0.96, 0.91]},
            "schema_changes": ["+ feature: promo_flag_v2", "- feature: promo_flag"],
        }
    raise NotImplementedError("Live mode requires registry wiring; set MENDRIFT_DEMO=1")