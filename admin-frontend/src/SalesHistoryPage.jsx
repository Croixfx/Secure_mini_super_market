// frontend-admin/SalesHistoryPage.jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminClient";
import RefundModal from "./RefundModal";

const STATUS_LABEL = {
  COMPLETED: null, // nothing to show — the normal, un-refunded state
  PARTIALLY_REFUNDED: "Partially refunded",
  REFUNDED: "Refunded",
};

export default function SalesHistoryPage() {
  const [sales, setSales] = useState([]);
  const [error, setError] = useState("");
  const [refundingSale, setRefundingSale] = useState(null);

  function load() {
    adminApi.listSales().then(setSales).catch((err) => setError(err.message));
  }
  useEffect(load, []);

  return (
    <div>
      <h1 className="admin-h1">Sales history</h1>
      <p className="admin-subtitle">Every completed sale, branch-scoped, traced back to its stock movements.</p>

      {error && <p style={{ color: "#C1443C" }}>{error}</p>}

      {sales.length === 0 ? (
        <div className="admin-empty">No sales recorded yet.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {sales.map((sale) => (
            <div className="admin-card" key={sale.id} style={{ padding: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <strong>Sale #{sale.id} — {sale.cashier_username}</strong>
                <span style={{ color: "#6B7280", fontSize: "0.85rem" }}>
                  {new Date(sale.created_at).toLocaleString()}
                </span>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                {sale.items.map((item) => (
                  <span key={item.id} className="admin-chip" data-level="normal" style={{ position: "static" }}>
                    {item.quantity}× {item.product_name}
                  </span>
                ))}
                {STATUS_LABEL[sale.status] && (
                  <span className="admin-chip" data-level="low" style={{ position: "static" }}>
                    {STATUS_LABEL[sale.status]}
                  </span>
                )}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.9rem" }}>
                <span style={{ color: "#6B7280" }}>{sale.payment_method}</span>
                <strong>{Number(sale.total_amount).toFixed(2)}</strong>
              </div>
              {sale.status !== "REFUNDED" && (
                <button
                  className="admin-button-secondary"
                  style={{ width: "100%", marginTop: 10 }}
                  onClick={() => setRefundingSale(sale)}
                >
                  Refund
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {refundingSale && (
        <RefundModal
          sale={refundingSale}
          onClose={() => setRefundingSale(null)}
          onRefunded={() => { setRefundingSale(null); load(); }}
        />
      )}
    </div>
  );
}
