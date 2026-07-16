"""mendrift-mcp server entry point.

Read-only diagnostics for ML incident response. Gated action tools
(rollback execution) arrive in Phase 3.
"""
from mcp.server.fastmcp import FastMCP

from mendrift_mcp.tools import monitoring

mcp = FastMCP(
    "mendrift-mcp",
    instructions=(
        "Drift detection and ML incident-response tools. Use get_drift_report "
        "and summarize_metric_anomalies to diagnose; use get_deployment_history "
        "and diff_deployments to correlate incidents with deploys."
    ),
)

mcp.tool()(monitoring.get_drift_report)
mcp.tool()(monitoring.summarize_metric_anomalies)
mcp.tool()(monitoring.get_deployment_history)
mcp.tool()(monitoring.diff_deployments)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()