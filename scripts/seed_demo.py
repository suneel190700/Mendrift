"""Seed a local MLflow registry with a realistic drift + regression scenario.

Creates the world the fixtures have been faking:
  v13 - depth 6, clean training window ending 2026-06-20, uses promo_flag
  v14 - depth 9, noisier window ending 2026-07-10, promo_flag -> promo_flag_v2

Both versions are scored on ONE common eval set drawn from the production
(shifted) distribution, so val_auc / val_recall are actually comparable.
Also writes reference/current parquet frames for real Evidently drift.

Run:  uv run mlflow server --host 127.0.0.1 --port 5000    (other terminal)
      PYTHONPATH=src uv run python scripts/seed_demo.py
"""
from __future__ import annotations

from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import recall_score, roc_auc_score

TRACKING_URI = "http://127.0.0.1:5001"
MODEL_NAME = "fraud-scorer"
DATA_DIR = Path("data")
PROMO_OLD = "promo_flag"
PROMO_NEW = "promo_flag_v2"
rng = np.random.default_rng(42)


def make_frame(n: int, shifted: bool, promo_col: str) -> pd.DataFrame:
    """Synthetic transactions. `shifted` moves distributions the way a real
    population shift would; promo_col carries the schema rename."""
    txn_amount_zscore = rng.normal(0.6 if shifted else 0.0, 1.0, n)
    merchant_category_freq = rng.beta(2, 5 if shifted else 8, n)
    hour_of_day = rng.integers(0, 24, n)
    account_age_days = rng.gamma(2.0, 300, n)
    promo = rng.binomial(1, 0.35 if shifted else 0.12, n)

    df = pd.DataFrame({
        "txn_amount_zscore": txn_amount_zscore,
        "merchant_category_freq": merchant_category_freq,
        "hour_of_day": hour_of_day,
        "account_age_days": account_age_days,
        promo_col: promo,
    })

    logit = (1.6 * txn_amount_zscore + 3.2 * merchant_category_freq
             - 0.0012 * account_age_days + 0.9 * promo - 1.4)
    p = 1 / (1 + np.exp(-logit))
    df["is_fraud"] = rng.binomial(1, p)
    return df


def score(model, eval_df: pd.DataFrame, promo_col: str) -> tuple[float, float]:
    """Score a model on the common eval set, renaming promo to its schema."""
    df = eval_df.rename(columns={"promo": promo_col})
    features = [c for c in df.columns if c != "is_fraud"]
    proba = model.predict_proba(df[features])[:, 1]
    preds = (proba >= 0.5).astype(int)
    return (float(roc_auc_score(df["is_fraud"], proba)),
            float(recall_score(df["is_fraud"], preds)))


def train_and_log(train_df: pd.DataFrame, eval_df: pd.DataFrame, run_name: str,
                  max_depth: int, training_data_end: str, promo_col: str,
                  label_noise: float = 0.0) -> tuple[float, float]:
    y = train_df["is_fraud"].to_numpy().copy()
    if label_noise:
        # missed-fraud labels: positives recorded as negatives (asymmetric,
        # the way late-discovered fraud actually corrupts a training window)
        pos = np.flatnonzero(y == 1)
        y[pos[rng.random(len(pos)) < label_noise]] = 0

    features = [c for c in train_df.columns if c != "is_fraud"]

    with mlflow.start_run(run_name=run_name):
        model = RandomForestClassifier(
            n_estimators=120, max_depth=max_depth, random_state=42)
        model.fit(train_df[features], y)

        auc, recall = score(model, eval_df, promo_col)

        mlflow.log_params({
            "max_depth": max_depth,
            "n_estimators": 120,
            "training_data_end": training_data_end,
            "label_noise": label_noise,
            "features": ",".join(features),
        })
        mlflow.log_metrics({"val_auc": auc, "val_recall": recall})
        mlflow.sklearn.log_model(
            model, name="model", registered_model_name=MODEL_NAME)
        print(f"{run_name:16s} depth={max_depth}  val_auc={auc:.3f}  val_recall={recall:.3f}")
        return auc, recall


def main() -> None:
    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment("fraud-scorer")
    DATA_DIR.mkdir(exist_ok=True)

    # Drift frames for Evidently (schema rename included).
    reference = make_frame(6000, shifted=False, promo_col=PROMO_OLD)
    current = make_frame(6000, shifted=True, promo_col=PROMO_NEW)
    # Raw storage keeps the old column alongside the new one — a schema swap in
    # the model's feature list does not delete history upstream. This is what
    # lets a rolled-back model resume scoring the current window.
    current[PROMO_OLD] = current[PROMO_NEW]
    reference.to_parquet(DATA_DIR / "reference.parquet")
    current.to_parquet(DATA_DIR / "current.parquet")
    print(f"wrote {DATA_DIR}/reference.parquet and current.parquet")

    # ONE common eval set from the production distribution.
    eval_common = make_frame(4000, shifted=True, promo_col="promo")

    train_v13 = make_frame(6000, shifted=False, promo_col=PROMO_OLD)
    train_v14 = make_frame(6000, shifted=True, promo_col=PROMO_NEW)
    # v14 miscodes the renamed promo feature — signal lost, not just renamed
    train_v14[PROMO_NEW] = rng.binomial(1, 0.35, len(train_v14))

    auc13, rec13 = train_and_log(
        train_v13, eval_common, "v13-baseline", max_depth=6,
        training_data_end="2026-06-20", promo_col=PROMO_OLD)
    auc14, rec14 = train_and_log(
        train_v14, eval_common, "v14-regression", max_depth=9,
        training_data_end="2026-07-10", promo_col=PROMO_NEW, label_noise=0.45)

    print(f"\ndelta: auc {auc13:.3f} -> {auc14:.3f} ({auc14 - auc13:+.3f}), "
          f"recall {rec13:.3f} -> {rec14:.3f} ({rec14 - rec13:+.3f})")
    if auc14 >= auc13 or rec14 >= rec13:
        print("WARNING: v14 is not worse — raise label_noise or depth before seeding")

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