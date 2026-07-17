"""Every trajectory fixture must pass all four checks against the real graph."""
import pytest

from mendrift.evals.simulate import load_trajectories, run_trajectory


@pytest.mark.parametrize("traj", load_trajectories(), ids=lambda t: t["name"])
def test_trajectory(traj):
    r = run_trajectory(traj)
    assert r.no_ungated_writes, f"SAFETY: ungated write in {r.name}: {r.details}"
    assert r.classification_ok, r.details
    assert r.tool_sequence_ok, r.details
    assert r.action_ok, r.details