// All backend communication lives here, so components stay presentational.
// In dev, Vite proxies /api -> http://127.0.0.1:8000 (see vite.config.js).
const BASE = "";

export async function diagnose(alert) {
  const r = await fetch(`${BASE}/api/diagnose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(alert),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Diagnosis failed");
  return data;
}

export async function decide(threadId, approve) {
  const r = await fetch(`${BASE}/api/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, approve }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Decision failed");
  return data;
}

export async function health() {
  try {
    const r = await fetch(`${BASE}/api/health`);
    return await r.json();
  } catch {
    return null;
  }
}
