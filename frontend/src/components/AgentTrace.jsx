import ApprovalGate from "./ApprovalGate";
import OutcomeBanner from "./OutcomeBanner";

function Pill({ text, kind }) {
  return <span className={`pill ${kind ? `pill--${kind}` : ""}`}>{text || "—"}</span>;
}

export default function AgentTrace({ state, loading, deciding, onDecide }) {
  if (loading) {
    return (
      <div className="trace">
        <div className="step step--done">
          <div className="step__label">running</div>
          <div className="step__body">
            <span className="spinner" /> classifying + diagnosing (calling Claude · pulling evidence)…
          </div>
        </div>
      </div>
    );
  }
  if (!state) {
    return (
      <div className="empty">
        Configure an alert and run it.<br />
        The agent's reasoning appears here, step by step.
      </div>
    );
  }
  const actionKind = state.recommended_action === "rollback" ? "danger"
    : state.recommended_action === "monitor" ? "warn" : "";

  // Which terminal outcome to show, if any: the post-decision outcome wins,
  // otherwise the diagnose-phase terminal outcome (noise / monitor / incident).
  const terminalOutcome = state.finalOutcome ?? (state.halted ? null : state.outcome);

  return (
    <div className="trace">
      <div className="step step--done">
        <div className="step__label">classified</div>
        <div className="step__body"><Pill text={state.classification} kind="signal" /></div>
      </div>
      <div className="step step--done">
        <div className="step__label">evidence gathered</div>
        <div className="step__body">
          <div className="calls">
            {(state.evidence_calls || []).length
              ? state.evidence_calls.map((c, i) => <span key={i} className="call">{c}</span>)
              : <span className="call">none</span>}
          </div>
        </div>
      </div>
      <div className="step step--done">
        <div className="step__label">
          diagnosis · proposed <Pill text={state.recommended_action} kind={actionKind} />
        </div>
        <div className="step__body"><div className="diag">{state.diagnosis || "—"}</div></div>
      </div>

      {/* Approval gate: only while halted and awaiting a decision */}
      {state.halted && state.proposal && !state.finalOutcome && (
        <div className="step step--gate">
          <div className="step__label">human approval required</div>
          <ApprovalGate proposal={state.proposal} deciding={deciding} onDecide={onDecide} />
        </div>
      )}

      {/* Exactly one terminal state, once we have an outcome */}
      {terminalOutcome && (
        <div className="step step--done">
          <div className="step__label">terminal state</div>
          <OutcomeBanner outcome={terminalOutcome} />
        </div>
      )}
    </div>
  );
}
