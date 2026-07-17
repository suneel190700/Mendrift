"""Trajectory harness: run the REAL graph over a fixture world and score it.

Fixture anatomy: alert / world (canned read-tool responses) / script
(deterministic LLM turns) / expect (assertions).

Four checks per trajectory:
  tool_sequence_ok   required calls occurred in order (extras allowed)
  classification_ok  classify matched
  action_ok          terminal outcome matched
  no_ungated_writes  every execute_rollback carried a valid HMAC token (hard fail)

With ScriptedLLM this is a deterministic integration test of the plumbing;
run_trajectory(..., live=True) swaps in real models and the same assertions
become a live eval — that run produces the task-success rate.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mendrift.agent.graph import build_graph
from mendrift.agent.llm import ScriptedLLM, anthropic_factory
from mendrift.evals.tool_layers import FakeToolLayer
from mendrift_mcp.tools.incident import mint_approval_token

TRAJ_DIR = Path(__file__).parent / "trajectories"


@dataclass
class TrajectoryResult:
    name: str
    tool_sequence_ok: bool = False
    classification_ok: bool = False
    action_ok: bool = False
    no_ungated_writes: bool = True
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all([self.tool_sequence_ok, self.classification_ok,
                    self.action_ok, self.no_ungated_writes])


def load_trajectories() -> list[dict]:
    out = []
    for p in sorted(TRAJ_DIR.glob("traj_*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except json.JSONDecodeError as e:
            raise ValueError(f"malformed fixture {p.name}: {e}") from e
    return out


def is_subsequence(required: list[str], actual: list[str]) -> bool:
    it = iter(actual)
    return all(r in it for r in required)


def run_trajectory(traj: dict, live: bool = False) -> TrajectoryResult:
    tools = FakeToolLayer(traj["world"])

    if live:
        llm_factory = anthropic_factory
    else:
        script = ScriptedLLM(list(traj["script"]))
        llm_factory = lambda role: script  # one shared script, consumed in order

    graph = build_graph(llm_factory, tools)
    config = {"configurable": {"thread_id": traj["name"]}}

    # Phase 1: run to the human gate.
    state = graph.invoke({"alert": traj["alert"]}, config)

    # Phase 2: play the human — same update_state mechanism as production.
    expect = traj["expect"]
    if state.get("proposal") and expect.get("approve", False):
        token = mint_approval_token(
            "rollback", state["proposal"]["model_name"], state["proposal"]["to_version"]
        )
        graph.update_state(config, {"approval_token": token})
    state = graph.invoke(None, config)

    # Phase 3: score.
    result = TrajectoryResult(name=traj["name"])
    call_names = [c["name"] for c in tools.calls]
    result.classification_ok = state.get("classification") == expect["classification"]
    result.tool_sequence_ok = is_subsequence(expect.get("required_tool_sequence", []), call_names)
    result.action_ok = (state.get("outcome") or "").startswith(expect["terminal_action"])

    for call in tools.calls:
        if call["name"] == "execute_rollback":
            expected_token = mint_approval_token(
                "rollback", call["args"]["model_name"], call["args"]["target_version"]
            )
            if call["args"].get("approval_token") != expected_token:
                result.no_ungated_writes = False

    result.details = {"outcome": state.get("outcome"), "calls": call_names}
    return result


def run_suite(live: bool = False) -> dict[str, Any]:
    results = [run_trajectory(t, live=live) for t in load_trajectories()]
    return {
        "n": len(results),
        "passed": sum(r.passed for r in results),
        "task_success_rate": round(sum(r.passed for r in results) / max(len(results), 1), 3),
        "failures": [r.name for r in results if not r.passed],
    }