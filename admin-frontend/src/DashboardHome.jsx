// frontend-admin/DashboardHome.jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminClient";

function stockLevel(row) {
  if (row.is_below_threshold) return "low";
  const threshold = row.product?.reorder_threshold ?? 10;
  return row.quantity >= threshold * 3 ? "high" : "normal";
}

export default function DashboardHome({ user, onNavigate }) {
  const [stock, setStock] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    adminApi.listStock().then(setStock).catch((err) => setError(err.message));
  }, []);

  return (
    <div>
      <h1 className="admin-h1">Welcome back, {user?.username}</h1>
      <p className="admin-subtitle">Here's what's happening across your branch today.</p>

      <div className="admin-quicklinks">
        <button className="admin-quicklink" onClick={() => onNavigate("inventory")}>
          <div className="icon">▤</div>
          <div className="title">Inventory</div>
          <div className="desc">View all of your inventory</div>
        </button>
        <button className="admin-quicklink" onClick={() => onNavigate("sales")}>
          <div className="icon">🧾</div>
          <div className="title">Sales</div>
          <div className="desc">View all of your recent sales</div>
        </button>
        <button className="admin-quicklink" onClick={() => onNavigate("purchase_orders")}>
          <div className="icon">▣</div>
          <div className="title">Purchase orders</div>
          <div className="desc">View your recent purchase orders</div>
        </button>
      </div>

      {error && <p style={{ color: "#C1443C" }}>{error}</p>}

      <h2 style={{ fontSize: "1.1rem", marginBottom: 14 }}>Inventory</h2>
      <table className="admin-table">
        <thead>
          <tr>
            <th>Product</th>
            <th>SKU</th>
            <th>Unit price</th>
            <th>Units available</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {stock.slice(0, 8).map((row) => (
            <tr key={row.id}>
              <td>{row.product.name}</td>
              <td>{row.product.sku}</td>
              <td>{Number(row.product.unit_price).toFixed(2)}</td>
              <td>{row.quantity}</td>
              <td>
                <span className="admin-chip" data-level={stockLevel(row)} style={{ position: "static" }}>
                  {stockLevel(row)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
