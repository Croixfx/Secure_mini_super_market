// frontend-admin/adminClient.js
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
    err.data = data; // lets callers check err.data.mfa_required, etc.
    throw err;
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export const adminApi = {
  // /auth/admin/... — NOT /auth/login/ etc. This app and pos-frontend share
  // one backend host, so a generic cookie name would let logging into one
  // app silently authenticate the other on its next load. The pos/admin
  // path prefix gives each app its own cookie namespace instead.
  login: (username, password) =>
    request("/auth/admin/login/", { method: "POST", body: { username, password }, auth: false }),
  // Step 2 of login for Owner/Manager accounts with a confirmed TOTP
  // device: same endpoint, same credentials, plus the 6-digit code. The
  // backend field name is "totp_code" (accounts/views.py:
  // CustomTokenObtainPairView.post reads request.data.get("totp_code")) —
  // confirmed against the real view, not guessed.
  loginWithMfa: (username, password, totpCode) =>
    request("/auth/admin/login/", {
      method: "POST",
      body: { username, password, totp_code: totpCode },
      auth: false,
    }),
  // Called once on app load to restore a session from the httpOnly refresh
  // cookie alone — no access token exists yet at this point, hence auth:
  // false. A rejection here (no cookie, or an expired/blacklisted one) is
  // the normal state for "not currently logged in," not an error to surface.
  refreshSilent: () => request("/auth/admin/refresh-silent/", { method: "POST", auth: false }),
  logout: () => request("/auth/admin/logout/", { method: "POST" }),
  // MFAEnrollView returns { secret, provisioning_uri, qr_code_base64 }.
  mfaEnroll: () => request("/auth/mfa/enroll/", { method: "POST" }),
  // MFAEnrollConfirmView reads request.data.get("totp_code") too — same
  // field name as login, confirmed against accounts/views.py.
  mfaConfirm: (code) => request("/auth/mfa/enroll/confirm/", { method: "POST", body: { totp_code: code } }),
  listStock: () => request("/inventory/stock/"),
  listProducts: (query = "") => request(`/inventory/products/${query ? `?search=${encodeURIComponent(query)}` : ""}`),
  listCategories: () => request("/inventory/categories/"),
  createProduct: (payload) => request("/inventory/products/", { method: "POST", body: payload }),
  listSales: () => request("/sales/history/"),
  listMovements: (productId) =>
    request(`/inventory/movements/${productId ? `?product=${productId}` : ""}`),

  listSuppliers: () => request("/procurement/suppliers/"),
  createSupplier: (payload) => request("/procurement/suppliers/", { method: "POST", body: payload }),

  listPurchaseOrders: () => request("/procurement/purchase-orders/"),
  createPurchaseOrder: (payload) => request("/procurement/purchase-orders/", { method: "POST", body: payload }),
  sendPurchaseOrder: (id) => request(`/procurement/purchase-orders/${id}/send/`, { method: "POST" }),
  receivePurchaseOrder: (id, receipts) =>
    request(`/procurement/purchase-orders/${id}/receive/`, { method: "POST", body: { receipts } }),

  listBranches: () => request("/branches/"),
  createBranch: (payload) => request("/branches/", { method: "POST", body: payload }),
  updateBranch: (id, payload) => request(`/branches/${id}/`, { method: "PATCH", body: payload }),

  // UserAdminViewSet (accounts/views.py) is mounted at /api/users/ —
  // confirmed against accounts/urls.py's router.register("users", ...)
  // and config/urls.py's path("api/", include("accounts.urls")).
  listStaff: () => request("/users/"),
  createStaff: (payload) => request("/users/", { method: "POST", body: payload }),
  updateStaff: (id, payload) => request(`/users/${id}/`, { method: "PATCH", body: payload }),
};
