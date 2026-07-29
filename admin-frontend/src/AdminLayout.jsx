// frontend-admin/AdminLayout.jsx
import "./admin-design.css";

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: "⌂" },
  { key: "inventory", label: "Inventory", icon: "▤" },
  { key: "sales", label: "Sales history", icon: "🧾" },
  { key: "purchase_orders", label: "Purchase orders", icon: "▣" },
  { key: "suppliers", label: "Suppliers", icon: "🚚" },
  { key: "mfa_settings", label: "Security", icon: "🔒" },
];

export default function AdminLayout({ page, onNavigate, user, onLogout, children }) {
  const initials = (user?.username || "?").slice(0, 2).toUpperCase();

  return (
    <div className="admin-root">
      <aside className="admin-sidebar">
        <div className="admin-brand">
          <span>🛒</span> Mini Supermarket
        </div>
        <nav className="admin-nav">
          {NAV_ITEMS.map((item) => (
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
