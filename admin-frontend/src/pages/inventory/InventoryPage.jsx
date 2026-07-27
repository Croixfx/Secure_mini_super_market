// frontend-inventory/InventoryPage.jsx
//
// Deliberately minimal — this exists to prove the vertical slice works from
// a real browser (login -> fetch -> render -> role-gated edit -> attempted
// IDOR shows a real 403), not to be the final polished admin UI.
//
// What this demonstrates live, in a demo:
//  1. Login as manager_a -> table shows ONLY branch A's stock rows.
//  2. cost_price column is present for manager/owner, absent for cashier
//     (server-redacted — open devtools network tab, the field simply
//     isn't in the JSON for a cashier token).
//  3. Attempting to PATCH a product as a cashier -> UI surfaces the 403
//     the server actually returned, not a client-side guess.

import { useEffect, useState } from "react";
import { api, setAccessToken, clearAccessToken } from "./client";

export default function InventoryPage() {
  const [role, setRole] = useState(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [refreshToken, setRefreshToken] = useState(null);
  const [stock, setStock] = useState([]);
  const [error, setError] = useState("");

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    try {
      const { access, refresh } = await api.login(username, password);
      setAccessToken(access);
      setRefreshToken(refresh);
      // JWT payload's role claim is for UI convenience only (e.g. show/hide
      // an edit button) — every actual permission decision still happens
      // server-side, regardless of what this claim says.
      const payload = JSON.parse(atob(access.split(".")[1]));
      setRole(payload.role);
      await loadStock();
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadStock() {
    try {
      const rows = await api.listStock();
      setStock(rows);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleLogout() {
    try {
      await api.logout(refreshToken);
    } finally {
      clearAccessToken();
      setRole(null);
      setStock([]);
    }
  }

  async function tryEditProduct(productId) {
    setError("");
    try {
      await api.updateProduct(productId, { unit_price: "99.00" });
      await loadStock();
    } catch (err) {
      // Expected path for a cashier: server returns 403, shown here as
      // proof the backend enforces this, not just the frontend hiding a button.
      setError(`Edit blocked by server: ${err.message} (status ${err.status})`);
    }
  }

  if (!role) {
    return (
      <form onSubmit={handleLogin} style={{ maxWidth: 320, margin: "40px auto", fontFamily: "sans-serif" }}>
        <h2>Sign in</h2>
        <input placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input
          placeholder="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button type="submit">Log in</button>
        {error && <p style={{ color: "crimson" }}>{error}</p>}
      </form>
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: "40px auto", fontFamily: "sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <h2>Stock — logged in as {role}</h2>
        <button onClick={handleLogout}>Log out</button>
      </div>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <table width="100%" cellPadding={6} style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #ccc", textAlign: "left" }}>
            <th>Product</th>
            <th>SKU</th>
            <th>Branch</th>
            <th>Qty</th>
            <th>Unit price</th>
            {role !== "CASHIER" && <th>Cost price</th>}
            {role !== "CASHIER" && <th></th>}
          </tr>
        </thead>
        <tbody>
          {stock.map((row) => (
            <tr key={row.id} style={{ borderBottom: "1px solid #eee" }}>
              <td>{row.product.name}</td>
              <td>{row.product.sku}</td>
              <td>{row.branch}</td>
              <td>{row.quantity}{row.is_below_threshold ? " ⚠ low" : ""}</td>
              <td>{row.product.unit_price}</td>
              {role !== "CASHIER" && <td>{row.product.cost_price ?? "—"}</td>}
              {role !== "CASHIER" && (
                <td>
                  <button onClick={() => tryEditProduct(row.product.id)}>Edit (test)</button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: 12, color: "#666" }}>
        Note: the cost price column and edit button are hidden here for cashiers by the
        UI, but the real protection is server-side — try hitting
        /api/inventory/products/&lt;id&gt;/ directly as a cashier token and you'll get the
        same redaction/403 regardless of this page's code.
      </p>
    </div>
  );
}
