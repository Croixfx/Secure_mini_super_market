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
  });

  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const data = await resp.json();
      detail = data.detail || JSON.stringify(data);
    } catch { /* not JSON */ }
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export const adminApi = {
  login: (username, password) =>
    request("/auth/login/", { method: "POST", body: { username, password }, auth: false }),
  listStock: () => request("/inventory/stock/"),
  listProducts: (query = "") => request(`/inventory/products/${query ? `?search=${encodeURIComponent(query)}` : ""}`),
  listCategories: () => request("/inventory/categories/"),
  createProduct: (payload) => request("/inventory/products/", { method: "POST", body: payload }),
  listSales: () => request("/sales/history/"),
  listMovements: (productId) =>
    request(`/inventory/movements/${productId ? `?product=${productId}` : ""}`),
};
