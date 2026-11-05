const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function handle(res) {
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON error page */
  }
  if (!res.ok) {
    const detail = data && typeof data.detail === "string" ? data.detail : null;
    throw new Error(detail || `Something went wrong (HTTP ${res.status}). Please try again.`);
  }
  return data;
}

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, options);
  } catch {
    throw new Error("Couldn't reach the server. It may be waking up (free hosting); please try again in a few seconds.");
  }
  return handle(res);
}

export function analyzeAgreement(file) {
  const form = new FormData();
  form.append("file", file, file.name);
  return request("/api/analyze", { method: "POST", body: form });
}

export function getAnalysis(id) {
  return request(`/api/analyses/${encodeURIComponent(id)}`);
}

/** Free Render instances sleep when idle; ping early so the server is awake by the time the user uploads. */
export function warmUp() {
  fetch(`${API_URL}/api/health`).catch(() => {});
}
