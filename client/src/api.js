export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : detail?.reason || detail?.code || `API request failed (${status})`);
    this.status = status; this.code = detail?.code;
  }
}
export async function apiRequest(path, { method = 'GET', body, signal } = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`${(import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')}${path}`, {
      method, signal: controller.signal,
      ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
    });
    let data;
    try { data = await response.json(); } catch { throw new ApiError(response.status, 'Invalid API response. Check the API URL/proxy.'); }
    if (!response.ok) throw new ApiError(response.status, Array.isArray(data.detail) ? 'Request rejected by backend validation.' : data.detail);
    return data;
  } finally { clearTimeout(timeout); signal?.removeEventListener('abort', abort); }
}
export function validateState(data) {
  if (data?.schema_version !== 'simulation-state-v1' || !Number.isInteger(data.tick) || !Number.isInteger(data.generation) ||
      !Array.isArray(data.approaches) || data.approaches.length !== 4 || !data.totals ||
      data.approaches.some(row => !['RED', 'YELLOW', 'GREEN'].includes(row.signal_color) ||
        !['LOW', 'MEDIUM', 'HIGH'].includes(row.congestion_level) ||
        !Number.isFinite(row.queue_length_vehicles) || !(row.countdown_seconds === null || Number.isFinite(row.countdown_seconds)))) {
    throw new ApiError(0, 'Backend state contract is unavailable or outdated. No substitute data is displayed.');
  }
  return data;
}
