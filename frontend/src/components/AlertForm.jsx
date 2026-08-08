// Two worlds, each with its own preset scenarios.
const WORLDS = {
  synthetic: {
    label: "Synthetic scenario",
    blurb: "A crafted fraud-scorer incident — clean, teachable schema-swap story.",
    presets: [
      { name: "Clean rollback case", source: "evidently", type: "drift", model_name: "fraud-scorer",
        detail: "PSI spike on merchant features ~1h after the v14 deploy; recall looks down" },
      { name: "Flapping / noise", source: "cloudwatch", type: "noise", model_name: "fraud-scorer",
        detail: "alert auto-resolved after 2 minutes, no sustained signal" },
      { name: "Seasonal — monitor", source: "evidently", type: "drift", model_name: "fraud-scorer",
        detail: "gradual PSI 0.18 on seasonality features over 3 weeks, no deploy in 6 weeks" },
      { name: "Upstream schema break", source: "evidently", type: "drift", model_name: "fraud-scorer",
        detail: "merchant_zip 100% null since 02:00, no deploy" },
      { name: "Tool outage — degrade", source: "evidently", type: "drift", model_name: "fraud-scorer",
        detail: "PSI spike but the drift report service is returning 500s" },
    ],
  },
  credit: {
    label: "Real US credit data",
    blurb: "Real US consumer-credit benchmark data with a controlled regression injected.",
    presets: [
      { name: "Default-rate collapse", source: "evidently", type: "drift", model_name: "credit-risk",
        detail: "default-rate alert on the older-borrower segment ~1h after the v2 model deploy; recall on defaulters looks down" },
      { name: "Income drift — monitor", source: "evidently", type: "drift", model_name: "credit-risk",
        detail: "gradual shift in MonthlyIncome distribution over several weeks, no recent deploy" },
      { name: "Flapping / noise", source: "cloudwatch", type: "noise", model_name: "credit-risk",
        detail: "credit-risk alert auto-resolved after 90 seconds, no sustained signal" },
      { name: "Utilization spike", source: "evidently", type: "drift", model_name: "credit-risk",
        detail: "RevolvingUtilization spikes right after the v2 deploy; approvals look off" },
    ],
  },
};

export default function AlertForm({ dataset, setDataset, alert, setAlert, onRun, running }) {
  const world = WORLDS[dataset] || WORLDS.synthetic;
  const presets = world.presets;
  const activePreset = alert.__preset;

  const pickWorld = (key) => {
    setDataset(key);
    // reset to that world's first preset
    setAlert({ ...WORLDS[key].presets[0], __preset: 0 });
  };
  const pickPreset = (i) => setAlert({ ...presets[i], __preset: i });
  const update = (field, value) => setAlert({ ...alert, [field]: value, __preset: null });

  return (
    <div className="panel">
      <div className="panel__head">incoming alert</div>
      <div className="panel__body">
        <label className="fld-label">Dataset</label>
        <div className="worldtoggle">
          {Object.entries(WORLDS).map(([key, w]) => (
            <button key={key}
              className={`worldbtn ${dataset === key ? "worldbtn--active" : ""}`}
              onClick={() => pickWorld(key)}>
              {w.label}
            </button>
          ))}
        </div>
        <div className="world-blurb">{world.blurb}</div>

        <label className="fld-label">Preset scenarios</label>
        <div className="presets">
          {presets.map((p, i) => (
            <button key={i}
              className={`preset ${activePreset === i ? "preset--active" : ""}`}
              onClick={() => pickPreset(i)}>
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

export { WORLDS };
