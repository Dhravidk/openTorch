const DEFAULT_BACKEND = "http://localhost:8000";

export function getBackendUrl() {
  return process.env.CGINS_BACKEND_URL || DEFAULT_BACKEND;
}

export async function jacSpawn(walkerName, payload = {}) {
  const backend = getBackendUrl();
  const res = await fetch(`${backend}/walker/${walkerName}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Jac walker ${walkerName} failed: ${res.status} ${text}`);
  }

  const data = await res.json();
  const reports =
    data?.data?.reports ||
    data?.data?.result?.reports ||
    data?.reports ||
    [];
  return { raw: data, reports };
}
