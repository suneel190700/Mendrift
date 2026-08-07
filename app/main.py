"""Mendrift live demo backend -- wraps the real agent graph behind HTTP."""
from __future__ import annotations

import os
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Point MLflow at a local sqlite store and force live mode BEFORE importing tools.
# local_tools.py defaults MENDRIFT_DEMO to "1"; setting it here first wins.
REPO_ROOT = Path(__file__).resolve().parent.parent
MLFLOW_DB = REPO_ROOT / "mlflow.db"
os.environ.setdefault("MLFLOW_TRACKING_URI", f"sqlite:///{MLFLOW_DB}")
os.environ.setdefault("MENDRIFT_DEMO", "0")
os.environ.setdefault("MENDRIFT_DATA_DIR", str(REPO_ROOT / "data"))

from mendrift.agent.graph import build_graph
from mendrift.agent.llm import anthropic_factory
from mendrift.agent.local_tools import LocalToolLayer
from mendrift_mcp.tools.incident import mint_approval_token


class RecordingToolLayer:
    """Wraps LocalToolLayer to record which tools were called, for the UI trace."""
    def __init__(self):
        self._inner = LocalToolLayer()
        self.calls: list[dict] = []

    def schemas(self):
        return self._inner.schemas()

    def call(self, name: str, args: dict) -> dict:
        self.calls.append({"name": name, "args": args})
        return self._inner.call(name, args)


app = FastAPI(title="Mendrift Live Demo", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"],
    allow_methods=["POST", "GET"], allow_headers=["*"],
)

_PENDING: dict[str, dict] = {}
_PENDING_LOCK = Lock()

_RATE: dict[str, deque] = defaultdict(deque)
_RATE_LOCK = Lock()
RATE_MAX = int(os.environ.get("DEMO_RATE_MAX", "8"))
RATE_WINDOW = int(os.environ.get("DEMO_RATE_WINDOW", "3600"))
DAILY_CAP = int(os.environ.get("DEMO_DAILY_CAP", "300"))
_daily = {"day": time.strftime("%Y-%m-%d"), "count": 0}
_DAILY_LOCK = Lock()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def _check_rate(ip: str) -> None:
    now = time.time()
    with _RATE_LOCK:
        q = _RATE[ip]
        while q and q[0] < now - RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_MAX:
            raise HTTPException(status_code=429,
                detail=f"Rate limit: {RATE_MAX} runs per hour. This demo calls a real model. "
                       "Clone the repo to run it locally without limits.")
        q.append(now)
    today = time.strftime("%Y-%m-%d")
    with _DAILY_LOCK:
        if _daily["day"] != today:
            _daily["day"], _daily["count"] = today, 0
        if _daily["count"] >= DAILY_CAP:
            raise HTTPException(status_code=429,
                detail="Daily demo budget reached -- resets at midnight UTC.")
        _daily["count"] += 1


class Alert(BaseModel):
    source: str = Field(default="evidently", max_length=40)
    type: str = Field(default="drift", max_length=40)
    model_name: str = Field(default="fraud-scorer", max_length=60)
    detail: str = Field(default="", max_length=400)


class Decision(BaseModel):
    thread_id: str
    approve: bool


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "registry_seeded": MLFLOW_DB.exists(),
            "daily_used": _daily["count"], "daily_cap": DAILY_CAP}


@app.post("/api/diagnose")
def diagnose(alert: Alert, request: Request) -> JSONResponse:
    _check_rate(_client_ip(request))
    tools = RecordingToolLayer()
    graph = build_graph(anthropic_factory, tools)
    thread_id = f"demo-{uuid.uuid4().hex[:12]}"
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = graph.invoke({"alert": alert.model_dump()}, config)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Agent run failed: {type(e).__name__}") from e
    calls = [c["name"] for c in getattr(tools, "calls", [])]
    proposal = state.get("proposal")
    if proposal and not state.get("outcome"):
        with _PENDING_LOCK:
            _PENDING[thread_id] = {"config": config, "graph": graph, "tools": tools, "created": time.time()}
        return JSONResponse({
            "thread_id": thread_id, "halted": True,
            "classification": state.get("classification"),
            "diagnosis": state.get("diagnosis"),
            "recommended_action": state.get("recommended_action"),
            "proposal": proposal, "evidence_calls": calls,
        })
    return JSONResponse({
        "thread_id": thread_id, "halted": False,
        "classification": state.get("classification"),
        "diagnosis": state.get("diagnosis"),
        "recommended_action": state.get("recommended_action"),
        "outcome": state.get("outcome"), "evidence_calls": calls,
    })


@app.post("/api/decision")
def decision(body: Decision) -> JSONResponse:
    with _PENDING_LOCK:
        pending = _PENDING.pop(body.thread_id, None)
    if not pending:
        raise HTTPException(status_code=404, detail="No pending incident with that id (it may have expired).")
    graph = pending["graph"]
    config = pending["config"]
    tools = pending["tools"]
    if body.approve:
        state = graph.get_state(config).values
        proposal = state["proposal"]
        token = mint_approval_token("rollback", proposal["model_name"], proposal["to_version"])
        graph.update_state(config, {"approval_token": token})
    try:
        final = graph.invoke(None, config)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Resume failed: {type(e).__name__}") from e
    calls = [c["name"] for c in getattr(tools, "calls", [])]
    return JSONResponse({
        "thread_id": body.thread_id, "approved": body.approve,
        "outcome": final.get("outcome"), "evidence_calls": calls,
    })


app.mount("/", StaticFiles(directory=str(REPO_ROOT / "frontend" / "dist"), html=True), name="static")
