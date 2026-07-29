// frontend-admin/AdminLayout.jsx
import "./admin-design.css";

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: "⌂" },
  { key: "inventory", label: "Inventory", icon: "▤" },
  { key: "sales", label: "Sales history", icon: "🧾" },
  // Backend already 403s a Cashier on these (IsBranchManagerOrOwner) —
  // this just keeps the nav from offering a link that only leads to an
  // error for that role.
  { key: "purchase_orders", label: "Purchase orders", icon: "▣", managerOnly: true },
  { key: "suppliers", label: "Suppliers", icon: "🚚", managerOnly: true },
  { key: "mfa_settings", label: "Security", icon: "🔒" },
  // Branch/staff management is Owner-only on the backend (IsOwner) — a
  // Manager has no business reason to open branches or manage accounts
  // across the whole business, only their own till/branch.
  { key: "branches", label: "Branches", icon: "🏬", ownerOnly: true },
  { key: "staff", label: "Staff", icon: "🧑‍💼", ownerOnly: true },
];

export default function AdminLayout({ page, onNavigate, user, onLogout, children }) {
  const initials = (user?.username || "?").slice(0, 2).toUpperCase();
  const navItems = NAV_ITEMS.filter(
    (item) =>
      (!item.managerOnly || user?.role !== "CASHIER") &&
      (!item.ownerOnly || user?.role === "OWNER")
  );

  return (
    <div className="admin-root">
      <aside className="admin-sidebar">
        <div className="admin-brand">
          <span>🛒</span> Mini Supermarket
        </div>
        <nav className="admin-nav">
          {navItems.map((item) => (
            <button
              key={item.key}
              className="admin-nav-item"
              data-active={page === item.key}
              onClick={() => onNavigate(item.key)}
            >
              <span>{item.icon}</span> {item.label}
            </button>
          ))}
        </nav>
        <div className="admin-user-footer">
          <div className="admin-user-avatar">{initials}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="admin-user-name">{user?.username}</div>
            <div className="admin-user-email">{user?.role}</div>
          </div>
          <button className="admin-nav-item" style={{ width: "auto" }} onClick={onLogout} title="Log out">⏻</button>
        </div>
      </aside>

      <main className="admin-main">
        <div className="admin-banner" />
        <div className="admin-content">{children}</div>
      </main>
    </div>
  );
}
