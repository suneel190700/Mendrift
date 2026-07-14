from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mendrift-mcp")

@mcp.tool()
def get_drift_report(model_name: str) -> dict:
    """Per-feature data drift for a deployed model (PSI/KS), with the top
    drifted features. Use when an alert suggests input distribution shift."""
    return {
        "model_name": model_name,
        "overall_drift": True,
        "n_features": 42,
        "n_drifted": 6,
        "top_drifted_features": [
            {"feature": "txn_amount_zscore", "psi": 0.31, "test": "PSI"},
            {"feature": "merchant_category_freq", "psi": 0.27, "test": "PSI"},
        ],
    }

def main() -> None:
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()