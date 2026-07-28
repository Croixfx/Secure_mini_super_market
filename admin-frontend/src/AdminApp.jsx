// frontend-admin/AdminApp.jsx
import { useState } from "react";
import { adminApi, setAccessToken, clearAccessToken } from "./adminClient";
import AdminLayout from "./AdminLayout";
import DashboardHome from "./DashboardHome";
import InventoryDashboardPage from "./InventoryDashboardPage";
import SalesHistoryPage from "./SalesHistoryPage";
import ComingSoonPage from "./ComingSoonPage";
import "./admin-design.css";

export default function AdminApp() {
  const [user, setUser] = useState(null);
  const [page, setPage] = useState("dashboard");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");

  async function handleLogin(e) {
    e.preventDefault();
    setLoginError("");
    try {
      const { access } = await adminApi.login(username, password);
      setAccessToken(access);
      const payload = JSON.parse(atob(access.split(".")[1]));
      setUser({ username, role: payload.role });
    } catch (err) {
      setLoginError(err.message);
    }
  }

  function handleLogout() {
    clearAccessToken();
    setUser(null);
    setPage("dashboard");
  }

  if (!user) {
    return (
      <div className="admin-root" style={{ display: "block" }}>
        <form
          onSubmit={handleLogin}
          style={{
            maxWidth: 340, margin: "12vh auto", background: "#fff",
            border: "1px solid #E7E4DC", borderRadius: 16, padding: 28,
            fontFamily: "Inter, system-ui, sans-serif",
          }}
        >
          <h1 style={{ fontSize: "1.3rem", marginBottom: 4 }}>Sign in</h1>
          <p style={{ color: "#6B7280", fontSize: "0.88rem", marginBottom: 20 }}>Admin dashboard</p>
          <div className="admin-field">
            <label>Username</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          </div>
          <div className="admin-field">
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button className="admin-button-primary" style={{ width: "100%" }} type="submit">Sign in</button>
          {loginError && <p style={{ color: "#C1443C", fontSize: "0.85rem", marginTop: 10 }}>{loginError}</p>}
        </form>
      </div>
    );
  }

  return (
    <AdminLayout page={page} onNavigate={setPage} user={user} onLogout={handleLogout}>
      {page === "dashboard" && <DashboardHome user={user} onNavigate={setPage} />}
      {page === "inventory" && <InventoryDashboardPage role={user.role} />}
      {page === "sales" && <SalesHistoryPage />}
      {page === "purchase_orders" && (
        <ComingSoonPage title="Purchase orders" description="Track orders to suppliers and receive stock against them." />
      )}
      {page === "suppliers" && (
        <ComingSoonPage title="Suppliers" description="Manage the suppliers you order stock from." />
      )}
    </AdminLayout>
  );
}
