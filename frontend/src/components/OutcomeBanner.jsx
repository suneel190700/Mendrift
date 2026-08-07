const LABELS = {
  resolved: "Resolved — rollback executed and recovery verified",
  closed_approval_denied: "Closed — rollback rejected, no action taken",
  closed_monitoring: "Closed — flagged for monitoring, no action needed",
  closed_as_noise: "Closed as noise — no substantive signal",
};

export default function OutcomeBanner({ outcome }) {
  const resolved = outcome === "resolved";
  const label = LABELS[outcome] || `Outcome: ${outcome || "—"}`;
  const icon = resolved ? "✓" : outcome === "closed_approval_denied" ? "✕" : "◆";
  return (
    <div className={`outcome ${resolved ? "outcome--ok" : "outcome--neutral"}`}>
      <span className="outcome__icon">{icon}</span>
      <div>
        <div className="outcome__label">{label}</div>
        <div className="outcome__code">outcome code: {outcome || "—"}</div>
      </div>
    </div>
  );
}
