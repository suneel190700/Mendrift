"""Seed a SECOND MLflow world using real US consumer-credit data.

Dataset: "Give Me Some Credit" (OpenML) — real US credit-risk records,
target SeriousDlqin2yrs (serious delinquency within 2 years).

This is the real-data counterpart to seed_demo.py. It does NOT touch the
synthetic `fraud-scorer` world — it registers a separate model, `credit-risk`.

Story: split by age into a reference window (younger borrowers) and a current
window (older borrowers) so genuine feature drift exists between them. Train a
clean v1 on the reference window; train v2 with an INJECTED regression
(asymmetric missed-default label noise + deeper trees) so it genuinely
underperforms — a controlled regression on real data, the standard way to give a
drift-detection system ground truth.

Run (embedded sqlite, same as seed_demo):
  PYTHONPATH=src MLFLOW_TRACKING_URI=sqlite:///$(pwd)/mlflow.db \
    uv run python scripts/seed_real.py
"""
from __future__ import annotations

import os
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.datasets import fetch_openml
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import recall_score, roc_auc_score

TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5001")
# Local artifact root so models save as plain files that load without a server
# (same fix as seed_demo.py — required for the embedded sqlite backend).
ARTIFACT_ROOT = Path(os.environ.get("MENDRIFT_ARTIFACT_ROOT", "mlruns")).resolve().as_uri()
MODEL_NAME = "credit-risk"
DATA_DIR = Path("data")
LABEL = "SeriousDlqin2yrs"
rng = np.random.default_rng(42)

# Features we keep from the dataset (drop the target; drop nothing else).
FEATURES = [
    "RevolvingUtilizationOfUnsecuredLines",
    "age",
    "NumberOfTime30-59DaysPastDueNotWorse",
    "DebtRatio",
    "MonthlyIncome",
    "NumberOfOpenCreditLinesAndLoans",
    "NumberOfTimes90DaysLate",
    "NumberRealEstateLoansOrLines",
    "NumberOfTime60-89DaysPastDueNotWorse",
    "NumberOfDependents",
]


def load_credit() -> pd.DataFrame:
    ds = fetch_openml(name="give-me-some-credit", version=1, as_frame=True, parser="auto")
    df = ds.frame.copy()
    df[LABEL] = df[LABEL].astype(int)
    # Drop rows missing the two commonly-null columns, keep it simple and clean.
    df = df.dropna(subset=["MonthlyIncome", "NumberOfDependents"]).reset_index(drop=True)
    return df


def score(model, eval_df: pd.DataFrame) -> tuple[float, float]:
    proba = model.predict_proba(eval_df[FEATURES])[:, 1]
    preds = (proba >= 0.5).astype(int)
    return (float(roc_auc_score(eval_df[LABEL], proba)),
            float(recall_score(eval_df[LABEL], preds)))


def train_and_log(train_df, eval_df, run_name, max_depth, training_data_end, label_noise=0.0):
    y = train_df[LABEL].to_numpy().copy()
    if label_noise:
        # missed-default labels: real defaults recorded as good (asymmetric),
        # the way late-discovered defaults corrupt a training window.
        pos = np.flatnonzero(y == 1)
        y[pos[rng.random(len(pos)) < label_noise]] = 0

    with mlflow.start_run(run_name=run_name):
        model = RandomForestClassifier(
            n_estimators=120, max_depth=max_depth, random_state=42,
            class_weight="balanced")
        model.fit(train_df[FEATURES], y)
        auc, recall = score(model, eval_df)
        mlflow.log_params({
            "max_depth": max_depth,
            "n_estimators": 120,
            "training_data_end": training_data_end,
            "label_noise": label_noise,
            "features": ",".join(FEATURES),
        })
        mlflow.log_metrics({"val_auc": auc, "val_recall": recall})
        mlflow.sklearn.log_model(model, name="model", registered_model_name=MODEL_NAME)
        print(f"{run_name:16s} depth={max_depth}  val_auc={auc:.3f}  val_recall={recall:.3f}")
        return auc, recall


def main() -> None:
    mlflow.set_tracking_uri(TRACKING_URI)
    if mlflow.get_experiment_by_name("credit-risk") is None:
        mlflow.create_experiment("credit-risk", artifact_location=ARTIFACT_ROOT)
    mlflow.set_experiment("credit-risk")
    DATA_DIR.mkdir(exist_ok=True)

    df = load_credit()
    # Real drift: split by age. Younger half = reference, older half = current.
    df = df.sort_values("age").reset_index(drop=True)
    n = len(df)
    reference = df.iloc[: n // 2].copy()
    current = df.iloc[n // 2:].copy()

    # Write the frames the drift tool reads (target included; tool excludes it).
    reference[FEATURES + [LABEL]].to_parquet(DATA_DIR / "reference_credit.parquet")
    current[FEATURES + [LABEL]].to_parquet(DATA_DIR / "current_credit.parquet")
    print(f"wrote {DATA_DIR}/reference_credit.parquet and current_credit.parquet")

    # Common eval = the current window (what production actually sees now).
    eval_common = current

    # v1: clean model on the reference window.
    auc1, rec1 = train_and_log(
        reference, eval_common, "v1-baseline", max_depth=8,
        training_data_end="2026-01-31")
    # v2: injected regression — missed-default label noise + deeper trees.
    auc2, rec2 = train_and_log(
        reference, eval_common, "v2-regression", max_depth=14,
        training_data_end="2026-06-30", label_noise=0.6)

    print(f"\ndelta: auc {auc1:.3f} -> {auc2:.3f} ({auc2 - auc1:+.3f}), "
          f"recall {rec1:.3f} -> {rec2:.3f} ({rec2 - rec1:+.3f})")
    if auc2 >= auc1 or rec2 >= rec1:
        print("WARNING: v2 is not worse — raise label_noise or depth before seeding")

    client = mlflow.MlflowClient()
    versions = sorted(client.search_model_versions(f"name='{MODEL_NAME}'"),
                      key=lambda v: int(v.version))
    latest = versions[-1].version
    previous = versions[-2].version if len(versions) > 1 else latest
    client.set_registered_model_alias(MODEL_NAME, "production", latest)
    client.set_registered_model_alias(MODEL_NAME, "previous", previous)
    print(f"aliases: production -> v{latest}, previous -> v{previous}")


if __name__ == "__main__":
    main()
