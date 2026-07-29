// frontend-admin/MfaSettingsPage.jsx
import { useState } from "react";
import { adminApi } from "./adminClient";
import "./admin-design.css";

export default function MfaSettingsPage({ user }) {
  const [step, setStep] = useState("start"); // start -> enrolling -> confirming -> done
  const [qrImage, setQrImage] = useState(null);
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const eligible = user?.role === "OWNER" || user?.role === "MANAGER";

  async function startEnrollment() {
    setError("");
    setLoading(true);
    try {
      const data = await adminApi.mfaEnroll();
      setQrImage(data.qr_code_base64);
      setSecret(data.secret);
      setStep("enrolling");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function confirmEnrollment(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await adminApi.mfaConfirm(code);
      setStep("done");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (!eligible) {
    return (
      <div>
        <h1 className="admin-h1">Two-factor authentication</h1>
        <div className="admin-empty">
          Two-factor authentication is only required for Owner and Manager
          accounts — cashier logins stay password-only for faster till
          turnover.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="admin-h1">Two-factor authentication</h1>
      <p className="admin-subtitle">
        Adds a second step to sign-in for Owner and Manager accounts, using
        any authenticator app (Google Authenticator, Authy, 1Password, etc).
      </p>

      {step === "start" && (
        <div className="admin-card" style={{ padding: 24, maxWidth: 420 }}>
          <p style={{ marginTop: 0, color: "var(--ink-soft)", fontSize: "0.9rem" }}>
            You haven't set up two-factor authentication yet. It takes about a minute.
          </p>
          <button className="admin-button-primary" onClick={startEnrollment} disabled={loading}>
            {loading ? "Starting…" : "Set up two-factor authentication"}
          </button>
          {error && <p style={{ color: "#C1443C", fontSize: "0.85rem", marginTop: 12 }}>{error}</p>}
        </div>
      )}

      {step === "enrolling" && (
        <div className="admin-card" style={{ padding: 24, maxWidth: 420 }}>
          <p style={{ fontWeight: 600, marginBottom: 4 }}>1. Scan this code</p>
          <p style={{ color: "var(--ink-soft)", fontSize: "0.85rem", marginBottom: 16 }}>
            Open your authenticator app and scan the QR code below.
          </p>
          {qrImage && (
            <img
              src={`data:image/png;base64,${qrImage}`}
              alt="Two-factor authentication QR code"
              style={{ display: "block", margin: "0 auto 16px", border: "1px solid var(--border)", borderRadius: 8 }}
              width={200} height={200}
            />
          )}
          <details style={{ marginBottom: 20, fontSize: "0.85rem" }}>
            <summary style={{ cursor: "pointer", color: "var(--ink-soft)" }}>
              Can't scan? Enter this code manually
            </summary>
            <code style={{
              display: "block", marginTop: 8, padding: "8px 10px",
              background: "var(--bg-page)", borderRadius: 6, wordBreak: "break-all",
              fontSize: "0.85rem",
            }}>
              {secret}
            </code>
          </details>

          <form onSubmit={confirmEnrollment}>
            <p style={{ fontWeight: 600, marginBottom: 8 }}>2. Enter the 6-digit code</p>
            <div className="admin-field">
              <input
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="123456"
                inputMode="numeric"
                autoFocus
                style={{ fontSize: "1.2rem", letterSpacing: "0.3em", textAlign: "center" }}
              />
            </div>
            {error && <p style={{ color: "#C1443C", fontSize: "0.85rem", marginBottom: 12 }}>{error}</p>}
            <button className="admin-button-primary" type="submit" disabled={loading || code.length !== 6}>
              {loading ? "Confirming…" : "Confirm and enable"}
            </button>
          </form>
        </div>
      )}

      {step === "done" && (
        <div className="admin-card" style={{ padding: 24, maxWidth: 420, textAlign: "center" }}>
          <div style={{ fontSize: "2rem", marginBottom: 8 }}>✓</div>
          <p style={{ fontWeight: 600 }}>Two-factor authentication is now enabled</p>
          <p style={{ color: "var(--ink-soft)", fontSize: "0.85rem" }}>
            You'll be asked for a code from your authenticator app the next time you sign in.
          </p>
        </div>
      )}
    </div>
  );
}
