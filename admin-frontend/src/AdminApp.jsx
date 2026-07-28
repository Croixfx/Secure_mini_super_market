// frontend-admin/AdminApp.jsx
import { useEffect, useState } from "react";
import { adminApi, setAccessToken, clearAccessToken } from "./adminClient";
import AdminLayout from "./AdminLayout";
import DashboardHome from "./DashboardHome";
import InventoryDashboardPage from "./InventoryDashboardPage";
import SalesHistoryPage from "./SalesHistoryPage";
import ComingSoonPage from "./ComingSoonPage";
import "./admin-design.css";

export default function AdminApp() {
  const [user, setUser] = useState(null);
  const [restoring, setRestoring] = useState(true);
  const [page, setPage] = useState("dashboard");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");

  function applyAccessToken(access) {
    setAccessToken(access);
    const payload = JSON.parse(atob(access.split(".")[1]));
    setUser({ username: payload.username, role: payload.role });
  }

  // Runs once on app load: a page refresh no longer means "log back in" —
  // if the browser still has a valid httpOnly refresh cookie from an
  // earlier login, this silently gets a fresh access token from it. A
  // rejection here (no cookie yet, or it expired) is just "not logged in,"
  // not an error to show.
  useEffect(() => {
    (async () => {
      try {
        const { access } = await adminApi.refreshSilent();
        applyAccessToken(access);
      } catch {
        // no session to restore — normal, land on the sign-in screen
      } finally {
        setRestoring(false);
      }
    })();
  }, []);

  async function handleLogin(e) {
    e.preventDefault();
    setLoginError("");
    try {
      const { access } = await adminApi.login(username, password);
      applyAccessToken(access);
    } catch (err) {
      setLoginError(err.message);
    }
  }

  async function handleLogout() {
    try {
      await adminApi.logout(); // blacklists the refresh token and clears its cookie server-side
    } catch {
      // Even if this fails (e.g. already expired), still clear client state
      // below — the goal is to end up logged out either way.
    }
    clearAccessToken();
    setUser(null);
    setPage("dashboard");
  }

  if (restoring) {
    return <div className="admin-root" />;
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
