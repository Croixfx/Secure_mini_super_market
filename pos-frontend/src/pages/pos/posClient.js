// frontend-pos/posClient.js
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

let accessToken = null;
export function setAccessToken(token) { accessToken = token; }
export function clearAccessToken() { accessToken = null; }

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    // Required so the browser sends/stores the httpOnly refresh cookie —
    // the refresh token itself is never readable by this JS, only the
    // cookie's presence/absence matters here.
    credentials: "include",
  });

  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    let data = {};
    try {
      data = await resp.json();
      detail = data.detail || JSON.stringify(data);
    } catch { /* not JSON */ }
    const err = new Error(detail);
    err.status = resp.status;
    err.data = data; // lets callers check err.data.mfa_required
    throw err;
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export const posApi = {
  // /auth/pos/... — NOT /auth/login/ etc. This app and admin-frontend share
  // one backend host, so a generic cookie name would let logging into one
  // app silently authenticate the other on its next load. The pos/admin
  // path prefix gives each app its own cookie namespace instead.
  login: (username, password) =>
    request("/auth/pos/login/", { method: "POST", body: { username, password }, auth: false }),
  // Step 2 for an Owner/Manager with a confirmed TOTP device (a cashier
  // never hits this — see MFA_REQUIRED_ROLES in accounts/views.py). Same
  // endpoint, same credentials, plus the code. Field name is "totp_code",
  // confirmed against CustomTokenObtainPairView.post, not guessed.
  loginWithMfa: (username, password, totpCode) =>
    request("/auth/pos/login/", {
      method: "POST",
      body: { username, password, totp_code: totpCode },
      auth: false,
    }),
  // Called once on app load to restore a session from the httpOnly refresh
  // cookie alone — no access token exists yet at this point, hence auth:
  // false. A rejection here (no cookie, or an expired/blacklisted one) is
  // the normal state for "not currently logged in," not an error to surface.
  refreshSilent: () => request("/auth/pos/refresh-silent/", { method: "POST", auth: false }),
  logout: () => request("/auth/pos/logout/", { method: "POST" }),
  searchProducts: (query) =>
    request(`/inventory/products/${query ? `?search=${encodeURIComponent(query)}` : ""}`),
  listStock: () => request("/inventory/stock/"),
  // idempotencyKey is generated ONCE per cart by the caller and reused on
  // retry — this is what makes a resubmitted checkout (flaky connection,
  // double-tap) safe rather than a double sale.
  checkout: (payload) => request("/sales/checkout/", { method: "POST", body: payload }),
};

export function newIdempotencyKey() {
  return crypto.randomUUID();
}
