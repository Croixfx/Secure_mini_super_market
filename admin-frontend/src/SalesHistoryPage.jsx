// frontend-admin/SalesHistoryPage.jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminClient";

export default function SalesHistoryPage() {
  const [sales, setSales] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    adminApi.listSales().then(setSales).catch((err) => setError(err.message));
  }, []);

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
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.9rem" }}>
                <span style={{ color: "#6B7280" }}>{sale.payment_method}</span>
                <strong>{Number(sale.total_amount).toFixed(2)}</strong>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
