// frontend-admin/MomoQRPage.jsx
//
// Requires: npm install qrcode  (in admin-frontend)
// Pure client-side QR generation — no backend call, no MTN developer
// account, no network dependency at all. This encodes a `tel:` URI, the
// same mechanism MTN's own printable MoMo Pay QR stickers use.
//
// IMPORTANT — what this actually does when scanned:
// A phone's camera/QR scanner reads a `tel:` link and offers to open the
// dialer pre-filled with the USSD string. The customer still has to tap
// "Call" themselves — no phone allows an app or QR code to silently
// dial on someone's behalf, since that would be a serious abuse vector
// (a malicious QR could otherwise dial premium numbers or trigger
// payments with zero consent). This is standard behavior, not a
// limitation specific to this implementation.
import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";

const DEFAULT_USSD = "*182*8*1*729710#";

function ussdToTelUri(ussd) {
  // USSD dial strings use * and # which must be percent-encoded inside a
  // tel: URI (RFC 3966) — otherwise many phones fail to parse it correctly.
  return "tel:" + ussd.replace(/\*/g, "%2A").replace(/#/g, "%23");
}

export default function MomoQRPage() {
  const [ussdCode, setUssdCode] = useState(
    () => localStorage.getItem("momoUssdCode") || DEFAULT_USSD
  );
  const [editing, setEditing] = useState(false);
  const [draftCode, setDraftCode] = useState(ussdCode);
  const canvasRef = useRef(null);

  useEffect(() => {
    if (canvasRef.current) {
      QRCode.toCanvas(canvasRef.current, ussdToTelUri(ussdCode), {
        width: 260,
        margin: 1,
        color: { dark: "#111318", light: "#FFFFFF" },
      });
    }
  }, [ussdCode]);

  function saveCode() {
    // Stored in localStorage only — this is a display setting, not a
    // secret or anything sensitive (the code is printed publicly at the
    // till anyway), so no backend/database field is needed for it.
    localStorage.setItem("momoUssdCode", draftCode);
    setUssdCode(draftCode);
    setEditing(false);
  }

  return (
    <div>
      <h1 className="admin-h1">MoMo Pay QR</h1>
      <p className="admin-subtitle">
        Print this and display it at the till. Customers scan it to open their
        phone's dialer pre-filled with your MoMo Pay code — they still confirm
        the call themselves, same as any MoMo Pay QR sticker.
      </p>

      <div className="admin-card" style={{ maxWidth: 360, padding: 24 }}>
        <div id="momo-qr-print-area" style={{ textAlign: "center" }}>
          <p style={{ fontWeight: 700, marginBottom: 4 }}>Scan to Pay with MoMo</p>
          <canvas ref={canvasRef} style={{ margin: "0 auto" }} />
          <p style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: "0.95rem", marginTop: 10 }}>
            {ussdCode}
          </p>
          <p style={{ fontSize: "0.78rem", color: "var(--ink-soft)" }}>
            QR not scanning? Dial the code above directly.
          </p>
        </div>

        {!editing ? (
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button className="admin-button-secondary" style={{ flex: 1 }} onClick={() => { setDraftCode(ussdCode); setEditing(true); }}>
              Edit code
            </button>
            <button className="admin-button-primary" style={{ flex: 1 }} onClick={() => window.print()}>
              Print
            </button>
          </div>
        ) : (
          <div style={{ marginTop: 16 }}>
            <div className="admin-field">
              <label>MoMo Pay USSD code</label>
              <input value={draftCode} onChange={(e) => setDraftCode(e.target.value)} placeholder="*182*8*1*729710#" />
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="admin-button-secondary" style={{ flex: 1 }} onClick={() => setEditing(false)}>Cancel</button>
              <button className="admin-button-primary" style={{ flex: 1 }} onClick={saveCode}>Save</button>
            </div>
          </div>
        )}
      </div>

      {/* Print isolation — same pattern as the receipt printing feature */}
      <style>{`
        @media print {
          body * { visibility: hidden; }
          #momo-qr-print-area, #momo-qr-print-area * { visibility: visible; }
          #momo-qr-print-area {
            position: absolute; left: 0; top: 0; width: 100%;
          }
        }
      `}</style>
    </div>
  );
}
