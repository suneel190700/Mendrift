const PRESETS = [
  { name: "Clean rollback case", source: "evidently", type: "drift", model_name: "fraud-scorer",
    detail: "PSI spike on merchant features ~1h after the v14 deploy; recall looks down" },
  { name: "Flapping / noise", source: "cloudwatch", type: "noise", model_name: "churn-predictor",
    detail: "alert auto-resolved after 2 minutes, no sustained signal" },
  { name: "Seasonal — monitor", source: "evidently", type: "drift", model_name: "demand-forecaster",
    detail: "gradual PSI 0.18 on seasonality features over 3 weeks, no deploy in 6 weeks" },
  { name: "Upstream schema break", source: "evidently", type: "drift", model_name: "fraud-scorer",
    detail: "merchant_zip 100% null since 02:00, no deploy" },
  { name: "Tool outage — degrade", source: "evidently", type: "drift", model_name: "aml-screener",
    detail: "PSI spike but the drift report service is returning 500s" },
];

export default function AlertForm({ alert, setAlert, onRun, running }) {
  const [activePreset, setActive] = [alert.__preset, (i) => setAlert({ ...PRESETS[i], __preset: i })];
  const update = (field, value) => setAlert({ ...alert, [field]: value, __preset: null });
  return (
    <div className="panel">
      <div className="panel__head">incoming alert</div>
      <div className="panel__body">
        <label className="fld-label">Preset scenarios</label>
        <div className="presets">
          {PRESETS.map((p, i) => (
            <button key={i}
              className={`preset ${activePreset === i ? "preset--active" : ""}`}
              onClick={() => setActive(i)}>
              {p.name}
            </button>
          ))}
        </div>
        <label className="fld-label">Source</label>
        <input value={alert.source} onChange={(e) => update("source", e.target.value)} />
        <label className="fld-label">Type</label>
        <select value={alert.type} onChange={(e) => update("type", e.target.value)}>
          <option>drift</option><option>quality</option><option>latency</option><option>noise</option>
        </select>
        <label className="fld-label">Model name</label>
        <input value={alert.model_name} onChange={(e) => update("model_name", e.target.value)} />
        <label className="fld-label">Symptom (what the alert reports — not your conclusion)</label>
        <textarea value={alert.detail} onChange={(e) => update("detail", e.target.value)} />
        <button className="run" onClick={onRun} disabled={running}>
          {running ? "running…" : "▶ run incident"}
        </button>
      </div>
    </div>
  );
}

export { PRESETS };
