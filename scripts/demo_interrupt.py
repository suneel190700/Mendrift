"""Kill-proof human gate demo.

Run:  uv run python scripts/demo_interrupt.py start   -> halts at gate, exits
Then: uv run python scripts/demo_interrupt.py approve -> NEW process resumes, finishes
Deny: uv run python scripts/demo_interrupt.py deny    -> NEW process closes without executing

The process fully exits between commands — state lives on disk in demo.db.
"""
import sqlite3
import sys
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from mendrift.agent.graph import build_graph
from mendrift.agent.llm import anthropic_factory
from mendrift.agent.local_tools import LocalToolLayer
from mendrift_mcp.tools.incident import mint_approval_token

CFG = {"configurable": {"thread_id": "incident-42"}}


def main():
    conn = sqlite3.connect("demo.db", check_same_thread=False)
    graph = build_graph(anthropic_factory, LocalToolLayer(), checkpointer=SqliteSaver(conn))

    cmd = sys.argv[1]

    if cmd == "start":
        # Reset the demo world along with the incident.
        Path("/tmp/mendrift_rollback_marker").unlink(missing_ok=True)
        state = graph.invoke(
            {"alert": {"model_name": "fraud-scorer", "type": "drift"}}, CFG
        )
        print("HALTED at human gate. Proposal:", state["proposal"])
        print("Process will now exit. State is on disk in demo.db.")

    elif cmd == "approve":
        state = graph.get_state(CFG).values
        p = state.get("proposal")
        if not p:
            print("Nothing to approve — no pending proposal.")
            print("Outcome:", state.get("outcome"), "| action:", state.get("recommended_action"))
            return
        token = mint_approval_token("rollback", p["model_name"], p["to_version"])
        graph.update_state(CFG, {"approval_token": token})
        state = graph.invoke(None, CFG)
        print("RESUMED after restart. Outcome:", state["outcome"])

    elif cmd == "deny":
        state = graph.invoke(None, CFG)
        print("RESUMED without approval. Outcome:", state["outcome"])

    else:
        print(f"unknown command: {cmd!r} — use start | approve | deny")


if __name__ == "__main__":
    main()