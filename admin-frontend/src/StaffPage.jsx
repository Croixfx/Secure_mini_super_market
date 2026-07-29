// frontend-admin/StaffPage.jsx
//
// NOTE FOR CLAUDE CODE: this assumes the existing UserAdminViewSet (built
// in accounts/views.py back in Feature 1) is reachable at /api/users/ —
// confirm the actual mount path in accounts/urls.py + config/urls.py and
// adjust adminApi.listStaff/createStaff/updateStaff in adminClient.js if
// it's mounted elsewhere.
import { useEffect, useState } from "react";
import { adminApi } from "./adminClient";

export default function StaffPage() {
  const [staff, setStaff] = useState([]);
  const [branches, setBranches] = useState([]);
  const [error, setError] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);

  function load() {
    adminApi.listStaff().then(setStaff).catch((err) => setError(err.message));
  }
  useEffect(() => {
    load();
    adminApi.listBranches().then(setBranches).catch(() => {});
  }, []);

  async function toggleActive(user) {
    setError("");
    try {
      await adminApi.updateStaff(user.id, { is_active: !user.is_active });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <h1 className="admin-h1">Staff</h1>
      <p className="admin-subtitle">Manage cashier and manager accounts across all branches.</p>

      <div className="admin-toolbar">
        <div style={{ flex: 1 }} />
        <button className="admin-button-primary" onClick={() => setShowModal(true)}>Add staff member</button>
      </div>

      {error && <p style={{ color: "#C1443C" }}>{error}</p>}

      <table className="admin-table">
        <thead>
          <tr>
            <th>Username</th><th>Role</th><th>Branch</th><th>Status</th><th></th>
          </tr>
        </thead>
        <tbody>
          {staff.map((u) => (
            <tr key={u.id}>
              <td>{u.username}</td>
              <td>{u.role}</td>
              <td>{branches.find((b) => b.id === u.branch)?.name || "—"}</td>
              <td>
                <span className="admin-chip" data-level={u.is_active ? "normal" : "low"} style={{ position: "static" }}>
                  {u.is_active ? "Active" : "Deactivated"}
                </span>
              </td>
              <td>
                <button className="admin-button-secondary" onClick={() => setEditingUser(u)}>Edit</button>
                {" "}
                <button className="admin-button-secondary" onClick={() => toggleActive(u)}>
                  {u.is_active ? "Deactivate" : "Reactivate"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {showModal && (
        <StaffModal
          branches={branches}
          onClose={() => setShowModal(false)}
          onSaved={() => { setShowModal(false); load(); }}
        />
      )}
      {editingUser && (
        <StaffModal
          branches={branches}
          existing={editingUser}
          onClose={() => setEditingUser(null)}
          onSaved={() => { setEditingUser(null); load(); }}
        />
      )}
    </div>
  );
}

function StaffModal({ branches, existing, onClose, onSaved }) {
  const [form, setForm] = useState({
    username: existing?.username || "",
    password: "",
    role: existing?.role || "CASHIER",
    branch: existing?.branch || "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const payload = { username: form.username, role: form.role, branch: form.branch || null };
      if (form.password) payload.password = form.password; // omit on edit if left blank
      if (existing) {
        await adminApi.updateStaff(existing.id, payload);
      } else {
        await adminApi.createStaff(payload);
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
          <h2>{existing ? "Edit staff member" : "Add staff member"}</h2>
          <button className="admin-modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="admin-field">
            <label>Username</label>
            <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required disabled={!!existing} />
          </div>
          <div className="admin-field">
            <label>{existing ? "New password (leave blank to keep current)" : "Password"}</label>
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required={!existing} minLength={10} />
          </div>
          <div className="admin-field">
            <label>Role</label>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="CASHIER">Cashier</option>
              <option value="MANAGER">Manager</option>
              <option value="OWNER">Owner</option>
            </select>
          </div>
          <div className="admin-field">
            <label>Branch</label>
            <select value={form.branch} onChange={(e) => setForm({ ...form, branch: e.target.value })}>
              <option value="">— None (Owner only) —</option>
              {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          {error && <p style={{ color: "#C1443C", fontSize: "0.85rem" }}>{error}</p>}
          <div className="admin-modal-actions">
            <button type="button" className="admin-button-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="admin-button-primary" disabled={submitting}>
              {submitting ? "Saving…" : existing ? "Save changes" : "Add staff member"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
