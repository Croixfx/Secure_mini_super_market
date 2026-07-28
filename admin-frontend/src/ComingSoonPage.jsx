// frontend-admin/ComingSoonPage.jsx
export default function ComingSoonPage({ title, description }) {
  return (
    <div>
      <h1 className="admin-h1">{title}</h1>
      <p className="admin-subtitle">{description}</p>
      <div className="admin-empty">
        This feature's backend hasn't been built yet — this page will connect
        to a real API once that app exists, same as Inventory and Sales.
      </div>
    </div>
  );
}
