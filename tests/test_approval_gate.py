"""The gate is the safety-critical unit: test it in isolation."""
from mendrift_mcp.tools.incident import execute_rollback, mint_approval_token


def test_forged_token_rejected():
    assert execute_rollback("m", "13", "forged")["status"] == "rejected"


def test_minted_token_executes():
    tok = mint_approval_token("rollback", "m", "13")
    assert execute_rollback("m", "13", tok)["status"] == "executed"


def test_token_is_action_scoped():
    tok = mint_approval_token("rollback", "m", "13")
    assert execute_rollback("m", "12", tok)["status"] == "rejected"   # wrong version
    assert execute_rollback("other", "13", tok)["status"] == "rejected"  # wrong model