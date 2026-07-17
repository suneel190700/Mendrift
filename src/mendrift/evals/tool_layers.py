"""Fake tool layer for trajectory tests: serves fixture 'world' data, records
every call, and delegates side-effectful tools to the REAL implementations so
the HMAC gate is exercised by every test — never mocked away.
Same contract as LocalToolLayer: schemas() / call(name, args).
"""
from __future__ import annotations

from typing import Any

from mendrift.agent.local_tools import SCHEMAS
from mendrift_mcp.tools import incident


class FakeToolLayer:
    def __init__(self, world: dict[str, Any]):
        self.world = world
        self.calls: list[dict] = []

    def schemas(self) -> list[dict]:
        return SCHEMAS

    def call(self, name: str, args: dict) -> dict:
        self.calls.append({"name": name, "args": args})
        if name == "execute_rollback":
            return incident.execute_rollback(**args)
        if name == "open_incident":
            return incident.open_incident(**args)
        if name == "propose_rollback":
            return incident.propose_rollback(**args)
        if name in self.world:
            resp = self.world[name]
            if isinstance(resp, dict) and "__raise__" in resp:
                raise RuntimeError(resp["__raise__"])
            return resp
        raise KeyError(f"fixture world has no response for tool '{name}'")