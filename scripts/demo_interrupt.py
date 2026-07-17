"""Kill-proof human gate demo.

Run:  uv run python scripts/demo_interrupt.py start   -> halts at gate, exit
Then: uv run python scripts/demo_interrupt.py approve -> resumes, finishes
The process fully exits between the two commands — state lives in demo.db.
"""
import sys

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

from mendrift.agent.graph import build_graph
from mendrift_mcp.tools.incident import mint_approval_token

CFG = {"configurable": {"thread_id": "incident-42"}}

def main():
    conn = sqlite3.connect("demo.db", check_same_thread=False)
    graph = build_graph(checkpointer=SqliteSaver(conn))

    cmd = sys.argv[1]

    if cmd == "start":
        state = graph.invoke(
            {"alert": {"model_name": "fraud-scorer", "type": "drift"}}, CFG
        )
        print("HALTED at human gate. Proposal:", state["proposal"])
        print("Process will now exit. State is on disk in demo.db.")

    elif cmd == "approve":
        state = graph.get_state(CFG).values
        p = state["proposal"]
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