// frontend-pos/Receipt.jsx
//
// Uses the browser's native print dialog (window.print()), styled to a
// 58mm width via print-specific CSS in receipt-print.css. This works with
// any thermal printer that has an OS-level driver (the common case for
// USB thermal printers) — no new backend, no local print-bridge service.
// A direct ESC/POS path is a documented future upgrade, not built here.
import "./receipt-print.css";

export default function Receipt({ sale, onClose }) {
  if (!sale) return null;

  const dateStr = new Date(sale.created_at).toLocaleString();

  return (
    <div className="receipt-overlay">
      <div className="receipt-preview-chrome">
        <button className="receipt-close-btn" onClick={onClose}>✕ Close</button>
        <button className="receipt-print-btn" onClick={() => window.print()}>🖨 Print receipt</button>
      </div>

      {/* Only this element is visible when the print dialog is triggered —
          see @media print rules in receipt-print.css */}
      <div id="receipt-print-area" className="receipt-58mm">
        <div className="receipt-center receipt-bold">MINI SUPERMARKET</div>
        <div className="receipt-center">{sale.branch_name}</div>
        <div className="receipt-divider" />

        <div className="receipt-row">
          <span>Receipt #{sale.id}</span>
        </div>
        <div className="receipt-row">
          <span>{dateStr}</span>
        </div>
        <div className="receipt-row">
          <span>Cashier: {sale.cashier_username}</span>
        </div>
        <div className="receipt-divider" />

        {sale.items.map((item) => (
          <div className="receipt-item" key={item.id}>
            <div className="receipt-item-name">{item.product_name}</div>
            <div className="receipt-row">
              <span>{item.quantity} x {Number(item.unit_price_at_sale).toFixed(2)}</span>
              <span>{Number(item.line_total).toFixed(2)}</span>
            </div>
          </div>
        ))}

        <div className="receipt-divider" />
        <div className="receipt-row receipt-bold receipt-total-row">
          <span>TOTAL</span>
          <span>{Number(sale.total_amount).toFixed(2)}</span>
        </div>
        <div className="receipt-row">
          <span>Payment</span>
          <span>{sale.payment_method}</span>
        </div>
        <div className="receipt-divider" />

        <div className="receipt-center receipt-small">Thank you for shopping with us</div>
        <div className="receipt-center receipt-small">Keep this receipt for returns (30 days)</div>
      </div>
    </div>
  );
}
