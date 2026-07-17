"""Run one trajectory by name (or all) — live or scripted.

Usage:
  PYTHONPATH=src uv run python scripts/run_traj.py rollback_proposed  --live
  PYTHONPATH=src uv run python scripts/run_traj.py --all              --live
  PYTHONPATH=src uv run python scripts/run_traj.py --all                        # scripted
"""
import json
import sys

from mendrift.evals.simulate import load_trajectories, run_suite, run_trajectory

live = "--live" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]

if "--all" in sys.argv or not args:
    print(json.dumps(run_suite(live=live), indent=2))
else:
    matches = [t for t in load_trajectories() if args[0] in t["name"]]
    if not matches:
        sys.exit(f"no trajectory matching {args[0]!r}")
    for t in matches:
        r = run_trajectory(t, live=live)
        print(f"{t['name']}: passed={r.passed}")
        print(json.dumps(r.details, indent=2))