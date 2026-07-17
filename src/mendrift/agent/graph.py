"""Incident graph: five nodes, one conditional edge, one human interrupt.

Nodes come from make_nodes(llm_factory, tools) — dependency injection, so
production passes real LLMs/tools and tests pass fakes. Same graph either way.
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from mendrift.agent.nodes import make_nodes


def _keep_latest(_old, new):
    return new


class IncidentState(TypedDict, total=False):
    alert: dict
    classification: Optional[str]
    evidence: Annotated[list, _keep_latest]
    diagnosis: Optional[str]
    recommended_action: Optional[str]
    target_version: Optional[str]
    proposal: Optional[dict]
    approval_token: Optional[str]   # written ONLY via graph.update_state()
    outcome: Optional[str]


def route_after_classify(state: IncidentState) -> Literal["diagnose", "close_noise"]:
    return "close_noise" if state["classification"] == "noise" else "diagnose"


def build_graph(llm_factory, tools, checkpointer=None):
    classify_alert, diagnose, propose, execute_and_verify = make_nodes(llm_factory, tools)

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