"""Incident graph skeleton — Phase 4: plumbing only, stub nodes.

alert -> classify -> (noise? close) -> diagnose -> propose -> [HUMAN GATE] -> execute_verify
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph


def _keep_latest(_old, new):
    return new


class IncidentState(TypedDict, total=False):
    alert: dict
    classification: Optional[str]
    evidence: Annotated[list, _keep_latest]
    diagnosis: Optional[str]
    proposal: Optional[dict]
    approval_token: Optional[str]   # written ONLY via graph.update_state()
    outcome: Optional[str]


# --- Phase 4 stubs: replaced by real LLM nodes in Phase 5 ---

def classify_alert(state: IncidentState) -> dict:
    return {"classification": "drift"}


def diagnose(state: IncidentState) -> dict:
    return {"diagnosis": "stub: v14 schema change correlates with drift",
            "evidence": [{"tool": "stub", "result": "stub"}]}


def propose(state: IncidentState) -> dict:
    return {"proposal": {"action": "rollback", "model_name": state["alert"]["model_name"],
                         "from_version": "14", "to_version": "13"}}


def execute_and_verify(state: IncidentState) -> dict:
    if not state.get("approval_token"):
        return {"outcome": "closed_approval_denied"}
    return {"outcome": "resolved"}


def route_after_classify(state: IncidentState) -> Literal["diagnose", "close_noise"]:
    return "close_noise" if state["classification"] == "noise" else "diagnose"


def build_graph(checkpointer=None):
    g = StateGraph(IncidentState)
    g.add_node("classify", classify_alert)
    g.add_node("diagnose", diagnose)
    g.add_node("propose", propose)
    g.add_node("execute_verify", execute_and_verify)
    g.add_node("close_noise", lambda s: {"outcome": "closed_as_noise"})

    g.set_entry_point("classify")
    g.add_conditional_edges("classify", route_after_classify)
    g.add_edge("diagnose", "propose")
    g.add_edge("propose", "execute_verify")
    g.add_edge("execute_verify", END)
    g.add_edge("close_noise", END)

    return g.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_before=["execute_verify"],
    )