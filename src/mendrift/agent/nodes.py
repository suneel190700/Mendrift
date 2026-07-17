"""Agent node implementations.

Each node: state in, partial state update out. Dependencies (llm_factory,
tools) arrive via closure from make_nodes — no globals, so tests can inject
fakes.

TOOL PROVIDER CONTRACT
    tools.schemas() -> list[dict]     # Anthropic tool-schema dicts
    tools.call(name, args) -> dict    # execute, return JSON-able result
"""
from __future__ import annotations

import json
import time

from mendrift.agent.llm import parse_json_content

MAX_TOOL_ITERATIONS = 8
TOOL_RETRIES = 2

CLASSIFY_PROMPT = """You are an ML incident triage classifier.
Given this monitoring alert, answer with ONLY a JSON object:
{{"classification": "<drift|latency|quality|noise>"}}

drift    - input/prediction distribution shift
latency  - serving latency or throughput regression
quality  - accuracy/recall/business-metric degradation
noise    - flapping alert, known maintenance, or insufficient signal

Alert:
{alert}"""

DIAGNOSE_SYSTEM = """You are an ML incident responder. Use the available tools to
find the root cause. Work evidence-first: pull the drift report and metric
anomalies, check what was deployed recently, and diff versions when a deploy
correlates with the alert. When you are confident, respond WITHOUT tool calls,
with ONLY this JSON:
{"diagnosis": "<root-cause narrative citing evidence>",
 "recommended_action": "<rollback|retrain|incident_only|none>",
 "target_version": "<version to roll back to, or null>"}"""

VERIFY_PROMPT = """Post-remediation check. Given these fresh serving metrics, answer
ONLY with JSON {{"recovered": true|false, "note": "<one line>"}}.
Metrics:
{metrics}"""


def make_nodes(llm_factory, tools):

    def classify_alert(state: dict) -> dict:
        llm = llm_factory("classify")
        resp = llm.invoke(
            [{"role": "user", "content": CLASSIFY_PROMPT.format(alert=json.dumps(state["alert"]))}]
        )
        parsed = parse_json_content(resp["content"], fallback={"classification": "noise"})
        label = parsed.get("classification", "noise")
        if label not in {"drift", "latency", "quality", "noise"}:
            label = "noise"  # fail-safe: unclassifiable must never trigger action
        return {"classification": label}

    def _call_tool_with_retries(name: str, args: dict) -> dict:
        last_err = None
        for attempt in range(TOOL_RETRIES + 1):
            try:
                return tools.call(name, args)
            except Exception as e:  # tool layer is untrusted
                last_err = e
                time.sleep(min(2**attempt * 0.1, 1.0))
        return {"tool_error": f"{name} failed after {TOOL_RETRIES + 1} attempts: {last_err}"}

    def diagnose(state: dict) -> dict:
        llm = llm_factory("diagnose")
        messages = [
            {"role": "user",
             "content": DIAGNOSE_SYSTEM + "\n\nAlert:\n" + json.dumps(state["alert"])
                        + f"\nClassification: {state['classification']}"},
        ]
        evidence = list(state.get("evidence", []))

        for _ in range(MAX_TOOL_ITERATIONS):
            resp = llm.invoke(messages, tools=tools.schemas())

            if not resp["tool_calls"]:
                parsed = parse_json_content(
                    resp["content"],
                    fallback={"diagnosis": resp["content"], "recommended_action": "incident_only"},
                )
                return {
                    "evidence": evidence,
                    "diagnosis": parsed.get("diagnosis", ""),
                    "recommended_action": parsed.get("recommended_action", "incident_only"),
                    "target_version": parsed.get("target_version"),
                }

            messages.append({"role": "assistant", "content": resp["content"] or "(calling tools)"})
            tool_results = []
            for tc in resp["tool_calls"]:
                result = _call_tool_with_retries(tc["name"], tc["args"])
                evidence.append({"tool": tc["name"], "args": tc["args"], "result": result})
                tool_results.append(f"[{tc['name']}] -> {json.dumps(result)}")
            messages.append({"role": "user", "content": "\n".join(tool_results)})

        return {
            "evidence": evidence,
            "diagnosis": "Exceeded tool budget; filing incident with partial evidence.",
            "recommended_action": "incident_only",
            "target_version": None,
        }

    def propose(state: dict) -> dict:
        action = state.get("recommended_action")
        model_name = state["alert"].get("model_name", "unknown")

        if action == "rollback" and state.get("target_version"):
            current = str(int(state["target_version"]) + 1)
            proposal = tools.call("propose_rollback", {
                "model_name": model_name,
                "current_version": current,
                "reason": state.get("diagnosis", ""),
            })
            return {"proposal": proposal, "outcome": None}

        if action in ("retrain", "incident_only"):
            incident = tools.call("open_incident", {
                "model_name": model_name,
                "severity": "sev2",
                "summary": f"{state['classification']} incident — {action} recommended",
                "diagnosis": state.get("diagnosis", ""),
            })
            return {"proposal": None, "outcome": f"incident_opened:{incident.get('incident_id')}"}

        return {"proposal": None, "outcome": "closed_no_action"}

    def execute_and_verify(state: dict) -> dict:
        proposal = state.get("proposal")
        if not proposal:
            return {"outcome": state.get("outcome") or "closed_no_action"}

        token = state.get("approval_token")
        if not token:
            return {"outcome": "closed_approval_denied"}

        result = tools.call("execute_rollback", {
            "model_name": proposal["model_name"],
            "target_version": proposal["to_version"],
            "approval_token": token,
        })
        if result.get("status") != "executed":
            return {"outcome": f"execution_rejected:{result.get('error', 'unknown')}"}

        metrics = tools.call("summarize_metric_anomalies", {"model_name": proposal["model_name"]})
        llm = llm_factory("verify")
        resp = llm.invoke([{"role": "user", "content": VERIFY_PROMPT.format(metrics=json.dumps(metrics))}])
        verdict = parse_json_content(resp["content"], fallback={"recovered": False})
        return {"outcome": "resolved" if verdict.get("recovered") else "rolled_back_not_recovered"}

    return classify_alert, diagnose, propose, execute_and_verify