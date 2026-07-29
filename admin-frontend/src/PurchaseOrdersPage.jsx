// frontend-admin/PurchaseOrdersPage.jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminClient";

const STATUS_LABEL = {
  DRAFT: "Draft", SENT: "Sent", PARTIALLY_RECEIVED: "Partially received",
  RECEIVED: "Received", CANCELLED: "Cancelled",
};

export default function PurchaseOrdersPage() {
  const [orders, setOrders] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [products, setProducts] = useState([]);
  const [error, setError] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [receivingOrder, setReceivingOrder] = useState(null);

  function load() {
    adminApi.listPurchaseOrders().then(setOrders).catch((err) => setError(err.message));
  }
  useEffect(() => {
    load();
    adminApi.listSuppliers().then(setSuppliers).catch(() => {});
    adminApi.listProducts().then(setProducts).catch(() => {});
  }, []);

  async function handleSend(orderId) {
    setError("");
    try {
      await adminApi.sendPurchaseOrder(orderId);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <h1 className="admin-h1">Purchase orders</h1>
      <p className="admin-subtitle">Order stock from suppliers, then receive it into your branch.</p>

      <div className="admin-toolbar">
        <div style={{ flex: 1 }} />
        <button className="admin-button-primary" onClick={() => setShowCreateModal(true)}>Create order</button>
      </div>

      {error && <p style={{ color: "#C1443C" }}>{error}</p>}

      {orders.length === 0 ? (
        <div className="admin-empty">No purchase orders yet — create one to start restocking.</div>
      ) : (
        <div className="admin-card-grid">
          {orders.map((po) => (
            <div className="admin-card" key={po.id} style={{ padding: 16 }}>
              <p className="admin-card-title">{po.supplier_name}</p>
              <div className="admin-card-row"><span>Cost</span><span className="value">{Number(po.total_cost).toFixed(2)}</span></div>
              <div className="admin-card-row"><span>Order made on</span><span className="value">{new Date(po.created_at).toLocaleDateString()}</span></div>
              <div style={{ margin: "8px 0" }}>
                <span className="admin-chip" data-level={po.status === "RECEIVED" ? "normal" : po.status === "CANCELLED" ? "low" : "high"} style={{ position: "static" }}>
                  {STATUS_LABEL[po.status]}
                </span>
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
                {po.items.slice(0, 2).map((item) => (
                  <span key={item.id} style={{ fontSize: "0.78rem", background: "var(--bg-page)", padding: "3px 8px", borderRadius: 999 }}>
                    {item.product_name}
                  </span>
                ))}
                {po.items.length > 2 && (
                  <span style={{ fontSize: "0.78rem", background: "var(--bg-page)", padding: "3px 8px", borderRadius: 999 }}>
                    +{po.items.length - 2}
                  </span>
                )}
              </div>
              {po.status === "DRAFT" && (
                <button className="admin-button-primary" style={{ width: "100%" }} onClick={() => handleSend(po.id)}>Send order</button>
              )}
              {(po.status === "SENT" || po.status === "PARTIALLY_RECEIVED") && (
                <button className="admin-button-primary" style={{ width: "100%" }} onClick={() => setReceivingOrder(po)}>Receive stock</button>
              )}
            </div>
          ))}
        </div>
      )}

      {showCreateModal && (
        <CreateOrderModal
          suppliers={suppliers}
          products={products}
          onClose={() => setShowCreateModal(false)}
          onCreated={() => { setShowCreateModal(false); load(); }}
        />
      )}
      {receivingOrder && (
        <ReceiveModal
          order={receivingOrder}
          onClose={() => setReceivingOrder(null)}
          onReceived={() => { setReceivingOrder(null); load(); }}
        />
      )}
    </div>
  );
}

function CreateOrderModal({ suppliers, products, onClose, onCreated }) {
  const [supplier, setSupplier] = useState("");
  const [lines, setLines] = useState([{ product: "", quantity_ordered: "", unit_cost: "" }]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function updateLine(index, field, value) {
    setLines((prev) => prev.map((line, i) => (i === index ? { ...line, [field]: value } : line)));
  }
  function addLine() {
    setLines((prev) => [...prev, { product: "", quantity_ordered: "", unit_cost: "" }]);
  }
  function removeLine(index) {
    setLines((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await adminApi.createPurchaseOrder({
        supplier,
        items: lines.map((l) => ({
          product: l.product, quantity_ordered: Number(l.quantity_ordered), unit_cost: l.unit_cost,
        })),
      });
      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="admin-modal-overlay" onClick={onClose}>
      <div className="admin-modal" style={{ width: 560 }} onClick={(e) => e.stopPropagation()}>
        <div className="admin-modal-header">
          <h2>Create purchase order</h2>
          <button className="admin-modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="admin-field">
            <label>Supplier</label>
            <select value={supplier} onChange={(e) => setSupplier(e.target.value)} required>
              <option value="">Select a supplier</option>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>

          <label style={{ fontSize: "0.85rem", fontWeight: 600, display: "block", marginBottom: 8 }}>Items</label>
          {lines.map((line, i) => (
            <div key={i} style={{ display: "flex", gap: 8, marginBottom: 10 }}>
              <select
                value={line.product}
                onChange={(e) => updateLine(i, "product", e.target.value)}
                style={{ flex: 2, padding: 8, border: "1px solid var(--border)", borderRadius: 8 }}
                required
              >
                <option value="">Product</option>
                {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <input
                type="number" min="1" placeholder="Qty" value={line.quantity_ordered}
                onChange={(e) => updateLine(i, "quantity_ordered", e.target.value)}
                style={{ flex: 1, padding: 8, border: "1px solid var(--border)", borderRadius: 8 }}
                required
              />
              <input
                type="number" step="0.01" min="0" placeholder="Unit cost" value={line.unit_cost}
                onChange={(e) => updateLine(i, "unit_cost", e.target.value)}
                style={{ flex: 1, padding: 8, border: "1px solid var(--border)", borderRadius: 8 }}
                required
              />
              {lines.length > 1 && (
                <button type="button" onClick={() => removeLine(i)} className="admin-button-secondary" style={{ padding: "8px 10px" }}>✕</button>
              )}
            </div>
          ))}
          <button type="button" className="admin-button-secondary" onClick={addLine} style={{ marginBottom: 16 }}>
            + Add item
          </button>

          {error && <p style={{ color: "#C1443C", fontSize: "0.85rem" }}>{error}</p>}
          <div className="admin-modal-actions">
            <button type="button" className="admin-button-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="admin-button-primary" disabled={submitting}>
              {submitting ? "Creating…" : "Create order"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ReceiveModal({ order, onClose, onReceived }) {
  const [quantities, setQuantities] = useState(
    Object.fromEntries(order.items.map((item) => [item.id, ""]))
  );
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    const receipts = order.items
      .filter((item) => Number(quantities[item.id]) > 0)
      .map((item) => ({ item_id: item.id, quantity: Number(quantities[item.id]) }));
    if (receipts.length === 0) {
      setError("Enter a quantity for at least one item.");
      setSubmitting(false);
      return;
    }
    try {
      await adminApi.receivePurchaseOrder(order.id, receipts);
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
          <h2>Receive stock — {order.supplier_name}</h2>
          <button className="admin-modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit}>
          {order.items.map((item) => (
            <div className="admin-field" key={item.id}>
              <label>{item.product_name} — {item.quantity_remaining} remaining of {item.quantity_ordered}</label>
              <input
                type="number" min="0" max={item.quantity_remaining}
                placeholder="Quantity received now"
                value={quantities[item.id]}
                onChange={(e) => setQuantities((prev) => ({ ...prev, [item.id]: e.target.value }))}
                disabled={item.quantity_remaining === 0}
              />
            </div>
          ))}
          {error && <p style={{ color: "#C1443C", fontSize: "0.85rem" }}>{error}</p>}
          <div className="admin-modal-actions">
            <button type="button" className="admin-button-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="admin-button-primary" disabled={submitting}>
              {submitting ? "Receiving…" : "Confirm receipt"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
