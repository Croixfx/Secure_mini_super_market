// frontend-admin/SuppliersPage.jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminClient";

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState([]);
  const [query, setQuery] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [error, setError] = useState("");

  function load() {
    adminApi.listSuppliers().then(setSuppliers).catch((err) => setError(err.message));
  }
  useEffect(load, []);

  const filtered = suppliers.filter((s) => s.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <div>
      <h1 className="admin-h1">Suppliers</h1>
      <p className="admin-subtitle">Companies you order stock from.</p>

      <div className="admin-toolbar">
        <input className="admin-search" placeholder="Search suppliers…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <button className="admin-button-primary" onClick={() => setShowModal(true)}>Add supplier</button>
      </div>

      {error && <p style={{ color: "#C1443C" }}>{error}</p>}

      {filtered.length === 0 ? (
        <div className="admin-empty">No suppliers yet — add one to start creating purchase orders.</div>
      ) : (
        <div className="admin-card-grid">
          {filtered.map((s) => (
            <div className="admin-card" key={s.id} style={{ padding: 16 }}>
              <p className="admin-card-title" style={{ marginBottom: 4 }}>{s.name}</p>
              {s.contact_name && <p style={{ color: "var(--ink-soft)", fontSize: "0.85rem", margin: "0 0 6px" }}>{s.contact_name}</p>}
              {s.email && <p style={{ fontSize: "0.85rem", margin: "0 0 4px" }}>{s.email}</p>}
              {s.phone && <p style={{ fontSize: "0.85rem", color: "var(--ink-soft)", margin: 0 }}>{s.phone}</p>}
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <AddSupplierModal onClose={() => setShowModal(false)} onCreated={() => { setShowModal(false); load(); }} />
      )}
    </div>
  );
}

function AddSupplierModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ name: "", contact_name: "", email: "", phone: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await adminApi.createSupplier(form);
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
          <h2>Add supplier</h2>
          <button className="admin-modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="admin-field">
            <label>Name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </div>
          <div className="admin-field">
            <label>Contact name</label>
            <input value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
          </div>
          <div className="admin-field">
            <label>Email</label>
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div className="admin-field">
            <label>Phone</label>
            <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
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
