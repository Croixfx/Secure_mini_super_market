// frontend-inventory/api/client.js
//
// Minimal fetch wrapper. Deliberately NOT using localStorage for tokens —
// access token lives in memory (module-level variable), refresh token is
// expected to be set as an httpOnly cookie by the backend on login (so JS
// can never read it, which is what actually defeats XSS-based token theft).
// For this early slice, access token is memory-only and lost on page
// refresh by design; wiring the httpOnly refresh cookie flow is a
// follow-up task, not a shortcut taken silently.

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

let accessToken = null;

export function setAccessToken(token) {
  accessToken = token;
}

export function clearAccessToken() {
  accessToken = null;
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include", // sends the httpOnly refresh cookie when that flow is wired up
  });

  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const data = await resp.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      // response wasn't JSON — keep the generic message
    }
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }

  if (resp.status === 204) return null;
  return resp.json();
}

export const api = {
  login: (username, password) =>
    request("/auth/login/", { method: "POST", body: { username, password }, auth: false }),
  logout: (refresh) => request("/auth/logout/", { method: "POST", body: { refresh } }),
  listStock: () => request("/inventory/stock/"),
  listProducts: () => request("/inventory/products/"),
  updateProduct: (id, patch) => request(`/inventory/products/${id}/`, { method: "PATCH", body: patch }),
};
