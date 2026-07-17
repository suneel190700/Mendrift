"""Generate trajectory variants from the archetype fixtures.

Clones each traj_00X archetype into N variants with varied model names,
versions, and feature-name suffixes — same structure, same expectations,
different surface. Because variants clone archetypes (which already carry
the evidence each expected action requires), they inherit correct evidence.
Deterministic seed, so the generated set is stable and committed.
"""
import copy
import json
import random
from pathlib import Path

TRAJ = Path("src/mendrift/evals/trajectories")
MODELS = ["fraud-scorer", "churn-predictor", "credit-risk-v2", "aml-screener", "limit-optimizer"]
random.seed(42)


def vary(traj: dict, i: int, model: str, prod_version: int) -> dict:
    old_model = traj["alert"]["model_name"]
    blob = json.dumps(traj)
    blob = blob.replace(old_model, model)
    # shift the 14/13 version pair the archetypes use
    blob = blob.replace('"14"', f'"{prod_version}"').replace('"13"', f'"{prod_version - 1}"')
    blob = blob.replace("promo_flag_v2", f"promo_flag_v{i + 2}")
    t = json.loads(blob)
    t["name"] = f"{traj['name']}_v{i}_{model}"
    return t


def main():
    # only archetypes traj_0*.json — never clone already-generated variants
    archetypes = sorted(TRAJ.glob("traj_0*.json"))
    # clear any prior generated batch so re-running is idempotent
    for old in TRAJ.glob("traj_1*.json"):
        old.unlink()

    n = 100
    for arch_path in archetypes:
        arch = json.loads(arch_path.read_text())
        for i, model in enumerate(random.sample(MODELS, 4)):
            variant = vary(arch, i, model, prod_version=random.randint(3, 30))
            (TRAJ / f"traj_{n}_{variant['name'][:40]}.json").write_text(json.dumps(variant, indent=2))
            n += 1
    print(f"wrote {n - 100} variants from {len(archetypes)} archetypes")


if __name__ == "__main__":
    main()