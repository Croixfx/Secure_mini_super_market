// frontend-admin/TransfersPage.jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminClient";

const STATUS_LEVEL = { REQUESTED: "high", IN_TRANSIT: "high", RECEIVED: "normal", CANCELLED: "low" };
const STATUS_LABEL = { REQUESTED: "Requested", IN_TRANSIT: "In transit", RECEIVED: "Received", CANCELLED: "Cancelled" };

export default function TransfersPage({ user }) {
  const [transfers, setTransfers] = useState([]);
  const [branches, setBranches] = useState([]);
  const [products, setProducts] = useState([]);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [receivingTransfer, setReceivingTransfer] = useState(null);

  function load() {
    adminApi.listTransfers().then(setTransfers).catch((err) => setError(err.message));
  }
  useEffect(() => {
    load();
    // Not listBranches — that's Owner-only (full BranchSerializer with
    // address/phone/staff_count). A Manager requesting a transfer still
    // needs to see other branches exist by name, hence the separate
    // id+name-only lookup endpoint.
    adminApi.listBranchesLookup().then(setBranches).catch(() => {});
    adminApi.listProducts().then(setProducts).catch(() => {});
  }, []);

  async function handleDispatch(id) {
    setError("");
    try {
      await adminApi.dispatchTransfer(id);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleCancel(id) {
    setError("");
    try {
      await adminApi.cancelTransfer(id);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <h1 className="admin-h1">Stock transfers</h1>
      <p className="admin-subtitle">Move stock between branches — dispatched by the source, confirmed by the destination.</p>

      <div className="admin-toolbar">
        <div style={{ flex: 1 }} />
        <button className="admin-button-primary" onClick={() => setShowCreate(true)}>Request transfer</button>
      </div>

      {error && <p style={{ color: "#C1443C" }}>{error}</p>}

      {transfers.length === 0 ? (
        <div className="admin-empty">No transfers yet.</div>
      ) : (
        <div className="admin-card-grid">
          {transfers.map((t) => (
            <div className="admin-card" key={t.id} style={{ padding: 16 }}>
              <p className="admin-card-title">{t.product_name}</p>
              <div className="admin-card-row"><span>From</span><span className="value">{t.from_branch_name}</span></div>
              <div className="admin-card-row"><span>To</span><span className="value">{t.to_branch_name}</span></div>
              <div className="admin-card-row"><span>Quantity</span><span className="value">{t.quantity_requested}</span></div>
              {t.discrepancy !== null && t.discrepancy > 0 && (
                <div className="admin-card-row"><span>Discrepancy</span><span className="value" style={{ color: "#C1443C" }}>-{t.discrepancy}</span></div>
              )}
              <div style={{ margin: "8px 0 12px" }}>
                <span className="admin-chip" data-level={STATUS_LEVEL[t.status]} style={{ position: "static" }}>
                  {STATUS_LABEL[t.status]}
                </span>
              </div>
              {t.status === "REQUESTED" && user.branch === t.from_branch && (
                <button className="admin-button-primary" style={{ width: "100%", marginBottom: 6 }} onClick={() => handleDispatch(t.id)}>
                  Dispatch
                </button>
              )}
              {t.status === "REQUESTED" && (
                <button className="admin-button-secondary" style={{ width: "100%" }} onClick={() => handleCancel(t.id)}>
                  Cancel request
                </button>
              )}
              {t.status === "IN_TRANSIT" && user.branch === t.to_branch && (
                <button className="admin-button-primary" style={{ width: "100%" }} onClick={() => setReceivingTransfer(t)}>
                  Confirm receipt
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateTransferModal
          branches={branches}
          products={products}
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); load(); }}
        />
      )}
      {receivingTransfer && (
        <ReceiveTransferModal
          transfer={receivingTransfer}
          onClose={() => setReceivingTransfer(null)}
          onReceived={() => { setReceivingTransfer(null); load(); }}
        />
      )}
    </div>
  );
}

function CreateTransferModal({ branches, products, onClose, onCreated }) {
  const [form, setForm] = useState({ product: "", from_branch: "", to_branch: "", quantity: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (form.from_branch === form.to_branch) {
      setError("Source and destination branches must be different.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await adminApi.createTransfer({ ...form, quantity: Number(form.quantity) });
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
          <h2>Request stock transfer</h2>
          <button className="admin-modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="admin-field">
            <label>Product</label>
            <select value={form.product} onChange={(e) => setForm({ ...form, product: e.target.value })} required>
              <option value="">Select a product</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div className="admin-field">
            <label>From branch</label>
            <select value={form.from_branch} onChange={(e) => setForm({ ...form, from_branch: e.target.value })} required>
              <option value="">Select source branch</option>
              {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          <div className="admin-field">
            <label>To branch</label>
            <select value={form.to_branch} onChange={(e) => setForm({ ...form, to_branch: e.target.value })} required>
              <option value="">Select destination branch</option>
              {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          <div className="admin-field">
            <label>Quantity</label>
            <input type="number" min="1" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} required />
          </div>
          {error && <p style={{ color: "#C1443C", fontSize: "0.85rem" }}>{error}</p>}
          <div className="admin-modal-actions">
            <button type="button" className="admin-button-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="admin-button-primary" disabled={submitting}>
              {submitting ? "Requesting…" : "Request transfer"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ReceiveTransferModal({ transfer, onClose, onReceived }) {
  const [quantity, setQuantity] = useState(transfer.quantity_requested);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await adminApi.receiveTransfer(transfer.id, Number(quantity));
      onReceived();
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
          <h2>Confirm receipt — {transfer.product_name}</h2>
          <button className="admin-modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit}>
          <p style={{ fontSize: "0.85rem", color: "var(--ink-soft)", marginBottom: 14 }}>
            {transfer.quantity_requested} units were dispatched from {transfer.from_branch_name}.
            Enter how many actually arrived — if fewer, the difference is recorded as a discrepancy.
          </p>
          <div className="admin-field">
            <label>Quantity received</label>
            <input
              type="number" min="0" max={transfer.quantity_requested}
              value={quantity} onChange={(e) => setQuantity(Math.min(Number(e.target.value), transfer.quantity_requested))}
              required
            />
          </div>
          {error && <p style={{ color: "#C1443C", fontSize: "0.85rem" }}>{error}</p>}
          <div className="admin-modal-actions">
            <button type="button" className="admin-button-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="admin-button-primary" disabled={submitting}>
              {submitting ? "Confirming…" : "Confirm receipt"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
