// frontend-admin/BranchesPage.jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminClient";

export default function BranchesPage() {
  const [branches, setBranches] = useState([]);
  const [error, setError] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);

  function load() {
    adminApi.listBranches().then(setBranches).catch((err) => setError(err.message));
  }
  useEffect(load, []);

  return (
    <div>
      <h1 className="admin-h1">Branches</h1>
      <p className="admin-subtitle">Every branch in your business, and how many staff are assigned to each.</p>

      <div className="admin-toolbar">
        <div style={{ flex: 1 }} />
        <button className="admin-button-primary" onClick={() => setShowModal(true)}>Add branch</button>
      </div>

      {error && <p style={{ color: "#C1443C" }}>{error}</p>}

      {branches.length === 0 ? (
        <div className="admin-empty">No branches yet — add your first one to start assigning staff and stock.</div>
      ) : (
        <div className="admin-card-grid">
          {branches.map((b) => (
            <div className="admin-card" key={b.id} style={{ padding: 16 }}>
              <p className="admin-card-title">{b.name}</p>
              {b.address && <p style={{ color: "var(--ink-soft)", fontSize: "0.85rem", margin: "0 0 4px" }}>{b.address}</p>}
              {b.phone && <p style={{ color: "var(--ink-soft)", fontSize: "0.85rem", margin: "0 0 8px" }}>{b.phone}</p>}
              <div className="admin-card-row"><span>Staff assigned</span><span className="value">{b.staff_count}</span></div>
              <button className="admin-button-secondary" style={{ width: "100%", marginTop: 10 }} onClick={() => setEditing(b)}>Edit</button>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <BranchModal onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); load(); }} />
      )}
      {editing && (
        <BranchModal existing={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

function BranchModal({ existing, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: existing?.name || "", address: existing?.address || "", phone: existing?.phone || "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      if (existing) {
        await adminApi.updateBranch(existing.id, form);
      } else {
        await adminApi.createBranch(form);
      }
      onSaved();
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
          <h2>{existing ? "Edit branch" : "Add branch"}</h2>
          <button className="admin-modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="admin-field">
            <label>Name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </div>
          <div className="admin-field">
            <label>Address</label>
            <input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          </div>
          <div className="admin-field">
            <label>Phone</label>
            <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </div>
          {error && <p style={{ color: "#C1443C", fontSize: "0.85rem" }}>{error}</p>}
          <div className="admin-modal-actions">
            <button type="button" className="admin-button-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="admin-button-primary" disabled={submitting}>
              {submitting ? "Saving…" : existing ? "Save changes" : "Add branch"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
