import { useState, useEffect } from "react";
import AlertForm, { PRESETS } from "./components/AlertForm";
import AgentTrace from "./components/AgentTrace";
import { diagnose, decide, health } from "./api";
import "./App.css";

export default function App() {
  const [alert, setAlert] = useState({ ...PRESETS[0], __preset: 0 });
  const [state, setState] = useState(null);
  const [running, setRunning] = useState(false);
  const [deciding, setDeciding] = useState(null);
  const [error, setError] = useState(null);
  const [warming, setWarming] = useState(false);

  useEffect(() => {
    health().then((h) => { if (h && !h.registry_seeded) setWarming(true); });
  }, []);

  async function handleRun() {
    setRunning(true); setError(null); setState(null);
    try {
      const { __preset, ...payload } = alert;
      const result = await diagnose(payload);
      setState(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  async function handleDecide(approve) {
    setDeciding(approve ? "approve" : "reject");
    try {
      const result = await decide(state.thread_id, approve);
      setState((s) => ({ ...s, halted: false, finalOutcome: result.outcome }));
    } catch (e) {
      setError(e.message);
    } finally {
      setDeciding(null);
    }
  }

  return (
    <div className="wrap">
      <header className="header">
        <div className="logo"><b>men</b>drift</div>
        <div className="tag">live incident console</div>
        <nav className="links">
          <a href="https://github.com/suneel190700/mendrift" target="_blank" rel="noreferrer">source</a>
          <a href="https://pypi.org/project/mendrift-mcp/" target="_blank" rel="noreferrer">pypi</a>
        </nav>
      </header>
      <p className="lede">
        A production model just fired a monitoring alert. <b>Mendrift investigates it live</b> —
        classifying the signal, pulling drift and registry evidence through its tools, and proposing
        a remediation. Destructive actions stop at a human approval gate. <b>You are the human.</b>
      </p>
      <div className="grid">
        <AlertForm alert={alert} setAlert={setAlert} onRun={handleRun} running={running} />
        <div className="panel">
          <div className="panel__head">agent trace</div>
          <div className="panel__body">
            {warming && !state && !running && (
              <div className="warming"><span className="spinner" /><br /><br />
                Backend is waking up / seeding its registry. Give it a moment, then run.</div>
            )}
            {error && <div className="error-box">{error}</div>}
            <AgentTrace state={state} loading={running} deciding={deciding} onDecide={handleDecide} />
          </div>
        </div>
      </div>
      <footer className="footer">
        Runs the real agent — live Claude reasoning over a real MLflow registry.
        Rate-limited because each run calls a real model.
      </footer>
    </div>
  );
}
