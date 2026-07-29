// frontend-admin/AdminApp.jsx
import { useEffect, useState } from "react";
import { adminApi, setAccessToken, clearAccessToken } from "./adminClient";
import AdminLayout from "./AdminLayout";
import DashboardHome from "./DashboardHome";
import InventoryDashboardPage from "./InventoryDashboardPage";
import SalesHistoryPage from "./SalesHistoryPage";
import MfaSettingsPage from "./MfaSettingsPage";
import PurchaseOrdersPage from "./PurchaseOrdersPage";
import SuppliersPage from "./SuppliersPage";
import BranchesPage from "./BranchesPage";
import StaffPage from "./StaffPage";
import TransfersPage from "./TransfersPage";
import "./admin-design.css";

export default function AdminApp() {
  const [user, setUser] = useState(null);
  const [restoring, setRestoring] = useState(true);
  const [page, setPage] = useState("dashboard");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaCode, setMfaCode] = useState("");
  const [loginError, setLoginError] = useState("");

  function applyAccessToken(access) {
    setAccessToken(access);
    const payload = JSON.parse(atob(access.split(".")[1]));
    // branch_id is in every JWT (CustomTokenObtainPairSerializer.get_token())
    // but was never surfaced here until TransfersPage needed it to decide
    // whether the logged-in manager is on the dispatching/receiving side of
    // a given transfer — without it, user.branch is always undefined and
    // those buttons would never appear for anyone.
    setUser({ username: payload.username, role: payload.role, branch: payload.branch_id });
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
      // Owner/Manager accounts with a confirmed TOTP device get a 401 here
      // with mfa_required: true instead of tokens — confirmed against
      // accounts/views.py: CustomTokenObtainPairView.post, not guessed.
      if (err.data?.mfa_required) {
        setMfaRequired(true);
        setLoginError("");
      } else {
        setLoginError(err.message);
      }
    }
  }

  async function handleMfaSubmit(e) {
    e.preventDefault();
    setLoginError("");
    try {
      const { access } = await adminApi.loginWithMfa(username, password, mfaCode);
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
    setMfaRequired(false);
    setMfaCode("");
    setPage("dashboard");
  }

  if (restoring) {
    return <div className="admin-root" />;
  }

  if (!user) {
    return (
      <div className="admin-root" style={{ display: "block" }}>
        <div style={{
          maxWidth: 340, margin: "12vh auto", background: "#fff",
          border: "1px solid #E7E4DC", borderRadius: 16, padding: 28,
          fontFamily: "Inter, system-ui, sans-serif",
        }}>
          {!mfaRequired ? (
            <form onSubmit={handleLogin}>
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
          ) : (
            <form onSubmit={handleMfaSubmit}>
              <h1 style={{ fontSize: "1.3rem", marginBottom: 4 }}>Enter your code</h1>
              <p style={{ color: "#6B7280", fontSize: "0.88rem", marginBottom: 20 }}>
                Open your authenticator app and enter the 6-digit code.
              </p>
              <div className="admin-field">
                <input
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="123456"
                  inputMode="numeric"
                  autoFocus
                  style={{ fontSize: "1.2rem", letterSpacing: "0.3em", textAlign: "center" }}
                />
              </div>
              <button className="admin-button-primary" style={{ width: "100%" }} type="submit" disabled={mfaCode.length !== 6}>
                Verify and sign in
              </button>
              <button
                type="button"
                className="admin-button-secondary"
                style={{ width: "100%", marginTop: 8 }}
                onClick={() => { setMfaRequired(false); setMfaCode(""); setLoginError(""); }}
              >
                Back
              </button>
              {loginError && <p style={{ color: "#C1443C", fontSize: "0.85rem", marginTop: 10 }}>{loginError}</p>}
            </form>
          )}
        </div>
      </div>
    );
  }

  return (
    <AdminLayout page={page} onNavigate={setPage} user={user} onLogout={handleLogout}>
      {page === "dashboard" && <DashboardHome user={user} onNavigate={setPage} />}
      {page === "inventory" && <InventoryDashboardPage role={user.role} />}
      {page === "sales" && <SalesHistoryPage />}
      {page === "mfa_settings" && <MfaSettingsPage user={user} />}
      {page === "purchase_orders" && <PurchaseOrdersPage />}
      {page === "suppliers" && <SuppliersPage />}
      {page === "branches" && <BranchesPage />}
      {page === "staff" && <StaffPage />}
      {page === "transfers" && <TransfersPage user={user} />}
    </AdminLayout>
  );
}
