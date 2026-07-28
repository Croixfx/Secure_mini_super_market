// frontend-admin/InventoryDashboardPage.jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminClient";

function stockLevel(row) {
  if (row.is_below_threshold) return "low";
  const threshold = row.product?.reorder_threshold ?? 10;
  return row.quantity >= threshold * 3 ? "high" : "normal";
}

export default function InventoryDashboardPage({ role }) {
  const [stock, setStock] = useState([]);
  const [query, setQuery] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const [error, setError] = useState("");

  function load() {
    adminApi.listStock().then(setStock).catch((err) => setError(err.message));
  }

  useEffect(load, []);

  const filtered = stock.filter((row) =>
    row.product.name.toLowerCase().includes(query.toLowerCase()) ||
    row.product.sku.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div>
      <h1 className="admin-h1">Inventory</h1>
      <p className="admin-subtitle">Stock levels for your branch, updated in real time from the sales ledger.</p>

      <div className="admin-toolbar">
        <input
          className="admin-search"
          placeholder="Search products…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {role !== "CASHIER" && (
          <button className="admin-button-primary" onClick={() => setShowAddModal(true)}>Add product</button>
        )}
      </div>

      {error && <p style={{ color: "#C1443C" }}>{error}</p>}

      {filtered.length === 0 ? (
        <div className="admin-empty">No products match your search yet.</div>
      ) : (
        <div className="admin-card-grid">
          {filtered.map((row) => (
            <div className="admin-card" key={row.id}>
              <div className="admin-card-media">
                <span className="admin-chip" data-level={stockLevel(row)}>{stockLevel(row)}</span>
                {row.product.name.slice(0, 2).toUpperCase()}
              </div>
              <div className="admin-card-body">
                <p className="admin-card-title">{row.product.name}</p>
                <div className="admin-card-row">
                  <span>Units available</span>
                  <span className="value">{row.quantity}</span>
                </div>
                {row.product.cost_price !== undefined && (
                  <div className="admin-card-row">
                    <span>Cost price</span>
                    <span className="value">{Number(row.product.cost_price).toFixed(2)}</span>
                  </div>
                )}
                <div className="admin-card-row">
                  <span>Sale price</span>
                  <span className="value">{Number(row.product.unit_price).toFixed(2)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showAddModal && (
        <AddProductModal
          onClose={() => setShowAddModal(false)}
          onCreated={() => { setShowAddModal(false); load(); }}
        />
      )}
    </div>
  );
}

function AddProductModal({ onClose, onCreated }) {
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState({ name: "", sku: "", category: "", unit_price: "", cost_price: "", reorder_threshold: 10 });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    adminApi.listCategories().then(setCategories).catch(() => {});
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await adminApi.createProduct(form);
      onCreated();
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
          <h2>Add new product</h2>
          <button className="admin-modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="admin-field">
            <label>Product name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </div>
          <div className="admin-field">
            <label>SKU</label>
            <input value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} required />
          </div>
          <div className="admin-field">
            <label>Category</label>
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} required>
              <option value="">Select a category</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div className="admin-field">
            <label>Cost price</label>
            <input type="number" step="0.01" value={form.cost_price} onChange={(e) => setForm({ ...form, cost_price: e.target.value })} required />
          </div>
          <div className="admin-field">
            <label>Sale price</label>
            <input type="number" step="0.01" value={form.unit_price} onChange={(e) => setForm({ ...form, unit_price: e.target.value })} required />
          </div>
          {error && <p style={{ color: "#C1443C", fontSize: "0.85rem" }}>{error}</p>}
          <div className="admin-modal-actions">
            <button type="button" className="admin-button-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="admin-button-primary" disabled={submitting}>
              {submitting ? "Adding…" : "Add"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
