export default function ApprovalGate({ proposal, deciding, onDecide }) {
  const p = proposal || {};
  return (
    <div className="gate">
      <div className="gate__head">
        <span className="gate__lock">🔒</span> HMAC-gated action · awaiting authorization
      </div>
      <div className="gate__body">
        {deciding ? (
          <div className="gate__working">
            <span className="spinner" />
            {deciding === "approve"
              ? " minting token · executing rollback · verifying recovery…"
              : " recording rejection…"}
          </div>
        ) : (
          <>
            <div className="gate__line">action: <b>{p.action || "rollback"}</b></div>
            <div className="gate__line">model: <b>{p.model_name}</b></div>
            <div className="gate__line">
              roll <b>v{String(p.from_version ?? "?")}</b> → <b>v{String(p.to_version ?? "?")}</b>
            </div>
            <div className="gate__actions">
              <button className="btn btn--approve" onClick={() => onDecide(true)}>
                ✓ approve rollback
              </button>
              <button className="btn btn--reject" onClick={() => onDecide(false)}>
                ✕ reject
              </button>
            </div>
            <div className="gate__note">
              The agent cannot execute this itself — it has no path to mint a token.
              Only your approval mints one.
            </div>
          </>
        )}
      </div>
    </div>
  );
}
