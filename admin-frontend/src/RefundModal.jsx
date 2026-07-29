// frontend-admin/RefundModal.jsx
// Launched from SalesHistoryPage — needs a "Refund" button added there per
// the wiring instructions (not modified directly here, to avoid clobbering
// whatever's changed in SalesHistoryPage.jsx since it was last handed off).
import { useState } from "react";
import { adminApi } from "./adminClient";

export default function RefundModal({ sale, onClose, onRefunded }) {
  const [reason, setReason] = useState("");
  const [lines, setLines] = useState(
    sale.items.map((item) => ({
      sale_item_id: item.id,
      product_name: item.product_name,
      // Remaining un-refunded quantity, not the original quantity sold —
      // otherwise a second partial refund could offer a max that's already
      // been (partly) refunded. Backend still enforces this independently;
      // this just keeps the UI from offering a quantity it would reject.
      max: item.quantity - item.quantity_refunded,
      quantity: 0,
      restock: true,
    }))
  );
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function updateLine(index, field, value) {
    setLines((prev) =>
      prev.map((l, i) => {
        if (i !== index) return l;
        // The number input's max attribute alone doesn't block anything —
        // handleSubmit calls e.preventDefault() before the browser's native
        // constraint validation would run, so a typed-in value above max
        // would otherwise sail straight through to the API. Clamp here so
        // the field is genuinely capped, not just decorated.
        if (field === "quantity") {
          value = Math.max(0, Math.min(Number(value) || 0, l.max));
        }
        return { ...l, [field]: value };
      })
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    const activeLines = lines.filter((l) => l.quantity > 0);
    if (activeLines.length === 0) {
      setError("Enter a quantity for at least one item.");
      return;
    }
    if (!reason.trim()) {
      setError("A reason is required for every refund.");
      return;
    }
    setSubmitting(true);
    try {
      await adminApi.refundSale(sale.id, {
        reason,
        lines: activeLines.map((l) => ({ sale_item_id: l.sale_item_id, quantity: l.quantity, restock: l.restock })),
      });
      onRefunded();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="admin-modal-overlay" onClick={onClose}>
      <div className="admin-modal" onClick={(e) => e.stopPropagation()}>
        <div className="admin-modal-header">
          <h2>Refund — Sale #{sale.id}</h2>
          <button className="admin-modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit}>
          {lines.map((line, i) => (
            <div key={line.sale_item_id} style={{ marginBottom: 16, paddingBottom: 12, borderBottom: "1px solid var(--border)" }}>
              <p style={{ fontWeight: 600, fontSize: "0.9rem", margin: "0 0 8px" }}>{line.product_name}</p>
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <input
                  type="number" min="0" max={line.max}
                  placeholder="Qty to refund"
                  value={line.quantity}
                  onChange={(e) => updateLine(i, "quantity", Number(e.target.value))}
                  style={{ flex: 1, padding: 8, border: "1px solid var(--border)", borderRadius: 8 }}
                />
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.85rem" }}>
                  <input
                    type="checkbox"
                    checked={line.restock}
                    onChange={(e) => updateLine(i, "restock", e.target.checked)}
                  />
                  Return to shelf
                </label>
              </div>
              {!line.restock && line.quantity > 0 && (
                <p style={{ fontSize: "0.78rem", color: "var(--ink-soft)", margin: "6px 0 0" }}>
                  Marked unsellable — will NOT be added back to stock.
                </p>
              )}
            </div>
          ))}

          <div className="admin-field">
            <label>Reason (required)</label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              placeholder="e.g. customer changed mind, item was expired, wrong item scanned"
              required
            />
          </div>

          {error && <p style={{ color: "#C1443C", fontSize: "0.85rem" }}>{error}</p>}
          <div className="admin-modal-actions">
            <button type="button" className="admin-button-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="admin-button-primary" disabled={submitting}>
              {submitting ? "Processing…" : "Process refund"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
