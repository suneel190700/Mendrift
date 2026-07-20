"""Read-only diagnostic tools: drift reports, anomaly summaries, deployment history.

In demo mode (MENDRIFT_DEMO=1) tools serve fixture data so the server is
demoable without live infrastructure. The demo world is minimally stateful:
after a rollback executes, metric anomalies come back clean.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _demo_mode() -> bool:
    return os.environ.get("MENDRIFT_DEMO", "0") == "1"


def get_drift_report(
    model_name: str,
    reference_window_hours: int = 168,
    current_window_hours: int = 24,
) -> dict[str, Any]:
    """Compute a data/prediction drift report for a deployed model.

    Compares the current serving window against a reference window (PSI + KS
    tests per feature). Returns per-feature drift scores, an overall drift
    flag, and the top drifted features.

    Args:
        model_name: Registered model name as it appears in the model registry.
        reference_window_hours: Reference window size (default 7 days).
        current_window_hours: Current window size (default 24 hours).
    """
    if _demo_mode():
        return {
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
    return _live_drift_report(model_name)


def _live_drift_report(model_name: str) -> dict[str, Any]:
    """Real drift: Evidently DataDriftPreset over reference vs current frames."""
    import pandas as pd
    from evidently import Dataset, DataDefinition, Report
    from evidently.presets import DataDriftPreset

    data_dir = Path(os.environ.get("MENDRIFT_DATA_DIR", "data"))
    reference = pd.read_parquet(data_dir / "reference.parquet")
    current = pd.read_parquet(data_dir / "current.parquet")

    # Schema changes are drift too — report columns added/removed between windows.
    ref_cols, cur_cols = set(reference.columns), set(current.columns)
    schema_changes = ([f"+ {c}" for c in sorted(cur_cols - ref_cols)]
                      + [f"- {c}" for c in sorted(ref_cols - cur_cols)])
    label_col = os.environ.get("MENDRIFT_LABEL_COL", "is_fraud")
    shared = sorted((ref_cols & cur_cols) - {label_col})

    definition = DataDefinition()
    ref_ds = Dataset.from_pandas(reference[shared], data_definition=definition)
    cur_ds = Dataset.from_pandas(current[shared], data_definition=definition)

    report = Report(metrics=[DataDriftPreset()])
    result = report.run(reference_data=ref_ds, current_data=cur_ds)
    payload = result.dict()

    # Evidently 0.7.x: per-column results are ValueDrift metrics whose `value`
    # is a DISTANCE (higher = more drift), judged against the metric's own
    # threshold. config carries column/method/threshold already parsed.
    scored = []
    for metric in payload.get("metrics", []):
        cfg = metric.get("config") or {}
        if not str(cfg.get("type", "")).endswith("ValueDrift"):
            continue
        value = metric.get("value")
        if not isinstance(value, (int, float)):
            continue
        threshold = float(cfg.get("threshold", 0.1))
        scored.append({
            "feature": cfg.get("column", "unknown"),
            "drift_score": round(float(value), 4),
            "threshold": threshold,
            "method": cfg.get("method", ""),
            "drifted": float(value) > threshold,
        })

    scored.sort(key=lambda d: d["drift_score"], reverse=True)
    significant = [d for d in scored if d["drifted"]]

    return {
        "model_name": model_name,
        "overall_drift": bool(significant or schema_changes),
        "n_features": len(shared),
        "n_drifted": len(significant),
        "top_drifted_features": significant[:5],
        "schema_changes": schema_changes,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": "evidently DataDriftPreset",
    }


def summarize_metric_anomalies(
    model_name: str,
    lookback_hours: int = 24,
) -> dict[str, Any]:
    """Summarize serving-metric anomalies (latency, error rate, prediction stats).

    Returns metric statistics with anomaly windows flagged via rolling z-score,
    suitable for an LLM to reason over without raw time series.
    """
    if _demo_mode():
        marker = Path("/tmp/mendrift_rollback_marker")
        if marker.exists() and marker.read_text().startswith(model_name):
            return {
                "model_name": model_name,
                "lookback_hours": lookback_hours,
                "anomalies": [],
                "note": "post-rollback window: anomalies cleared",
            }
        return {
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
    return _live_metric_anomalies(model_name, lookback_hours)


def _live_metric_anomalies(model_name: str, lookback_hours: int) -> dict[str, Any]:
    """Model-health check on current traffic.

    Data drift is already covered by get_drift_report. This tool answers a
    different question: is the SERVING model behaving anomalously? It scores
    the current window with the production model and with the previous
    version, and flags divergence between them. A rollback that fixes a bad
    release shows up here as the divergence disappearing; ordinary population
    drift does not fire, because both models shift together.
    """
    import mlflow
    import pandas as pd

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5001"))
    data_dir = Path(os.environ.get("MENDRIFT_DATA_DIR", "data"))
    current = pd.read_parquet(data_dir / "current.parquet")

    def rate(alias: str) -> float | None:
        try:
            model = mlflow.sklearn.load_model(f"models:/{model_name}@{alias}")
        except Exception:
            return None
        frame = current.reindex(columns=list(model.feature_names_in_))
        if frame.isna().all().any():
            return None   # this model cannot score current traffic at all
        return float((model.predict_proba(frame)[:, 1] >= 0.5).mean())

    prod_rate = rate("production")
    prev_rate = rate("previous")

    anomalies = []
    if prod_rate is None:
        anomalies.append({
            "metric": "scoring_schema_mismatch",
            "detail": "production model cannot score the current window — feature schema differs",
        })
    elif prev_rate is not None and prev_rate > 0:
        divergence = abs(prod_rate - prev_rate) / prev_rate
        if divergence > 0.20:
            anomalies.append({
                "metric": "prediction_rate_divergence_vs_previous_version",
                "production_rate": round(prod_rate, 4),
                "previous_version_rate": round(prev_rate, 4),
                "relative_divergence": round(divergence, 3),
                "detail": "serving model scores current traffic very differently "
                          "from the prior version — model-induced, not population drift",
            })

    return {"model_name": model_name, "lookback_hours": lookback_hours,
            "anomalies": anomalies,
            "source": "production vs previous version scored on the current window"}


def get_deployment_history(model_name: str, limit: int = 10) -> dict[str, Any]:
    """List recent deployments/version transitions for a model, newest first."""
    if _demo_mode():
        return {
            "model_name": model_name,
            "deployments": [
                {"version": "14", "stage": "Production", "deployed_at": "2026-07-12T08:05:00Z", "run_id": "run_f83a"},
                {"version": "13", "stage": "Archived", "deployed_at": "2026-07-02T14:11:00Z", "run_id": "run_c19d"},
            ][:limit],
        }
    return _live_deployment_history(model_name, limit)


def _client():
    import mlflow
    from mlflow import MlflowClient

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5001"))
    return MlflowClient()


def _live_deployment_history(model_name: str, limit: int) -> dict[str, Any]:
    """Real version transitions from the MLflow model registry."""
    client = _client()
    versions = sorted(
        client.search_model_versions(f"name='{model_name}'"),
        key=lambda v: int(v.version), reverse=True)[:limit]

    # Aliases live on the registered model, not on the version objects.
    registered = client.get_registered_model(model_name)
    alias_by_version: dict[str, list[str]] = {}
    for alias, version in (getattr(registered, "aliases", {}) or {}).items():
        alias_by_version.setdefault(str(version), []).append(alias)

    deployments = []
    for v in versions:
        aliases = alias_by_version.get(str(v.version), [])
        deployments.append({
            "version": v.version,
            "aliases": aliases,
            "stage": "Production" if "production" in aliases else "Archived",
            "deployed_at": datetime.fromtimestamp(
                v.creation_timestamp / 1000, tz=timezone.utc).isoformat(),
            "run_id": v.run_id,
        })
    return {"model_name": model_name, "deployments": deployments,
            "source": "mlflow model registry"}


def diff_deployments(model_name: str, version_a: str, version_b: str) -> dict[str, Any]:
    """Diff two model versions: training data span, params, eval metrics, feature schema.

    The primary root-cause tool: correlates 'what changed' between the incumbent
    and the newly deployed version.
    """
    if _demo_mode():
        return {
            "model_name": model_name,
            "version_a": version_a,
            "version_b": version_b,
            "param_diffs": {"max_depth": ["6", "9"], "training_data_end": ["2026-06-20", "2026-07-10"]},
            "metric_diffs": {"val_auc": [0.912, 0.905], "val_recall": [0.96, 0.91]},
            "schema_changes": ["+ feature: promo_flag_v2", "- feature: promo_flag"],
        }
    return _live_diff(model_name, version_a, version_b)


def _live_diff(model_name: str, version_a: str, version_b: str) -> dict[str, Any]:
    """Real params/metrics/schema diff between two registered versions."""
    client = _client()

    def run_data(version: str):
        mv = client.get_model_version(model_name, version)
        run = client.get_run(mv.run_id)
        return run.data.params, run.data.metrics

    params_a, metrics_a = run_data(version_a)
    params_b, metrics_b = run_data(version_b)

    param_diffs = {k: [params_a.get(k), params_b.get(k)]
                   for k in sorted(set(params_a) | set(params_b))
                   if params_a.get(k) != params_b.get(k) and k != "features"}
    metric_diffs = {k: [round(metrics_a.get(k, float("nan")), 4),
                        round(metrics_b.get(k, float("nan")), 4)]
                    for k in sorted(set(metrics_a) | set(metrics_b))
                    if metrics_a.get(k) != metrics_b.get(k)}

    feats_a = set(filter(None, params_a.get("features", "").split(",")))
    feats_b = set(filter(None, params_b.get("features", "").split(",")))
    schema_changes = ([f"+ feature: {c}" for c in sorted(feats_b - feats_a)]
                      + [f"- feature: {c}" for c in sorted(feats_a - feats_b)])

    return {"model_name": model_name, "version_a": version_a, "version_b": version_b,
            "param_diffs": param_diffs, "metric_diffs": metric_diffs,
            "schema_changes": schema_changes, "source": "mlflow runs"}