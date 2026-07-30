// frontend-pos/POSTerminal.jsx
import { useEffect, useMemo, useState } from "react";
import { posApi, setAccessToken, clearAccessToken, newIdempotencyKey } from "./posClient";
import Receipt from "./Receipt";
import "./pos-terminal.css";

export default function POSTerminal() {
  const [role, setRole] = useState(null);
  const [restoring, setRestoring] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaCode, setMfaCode] = useState("");
  const [loginError, setLoginError] = useState("");

  const [query, setQuery] = useState("");
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState([]); // [{product, quantity}]
  const [paymentMethod, setPaymentMethod] = useState("CASH");
  const [checkoutError, setCheckoutError] = useState("");
  const [receipt, setReceipt] = useState(null);
  const [showReceipt, setShowReceipt] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey());
  const [submitting, setSubmitting] = useState(false);

  function applyAccessToken(access) {
    setAccessToken(access);
    const payload = JSON.parse(atob(access.split(".")[1]));
    setRole(payload.role);
  }

  // Runs once on app load: a page refresh no longer means "log back in" —
  // if the browser still has a valid httpOnly refresh cookie from an
  // earlier login, this silently gets a fresh access token from it. A
  // rejection here (no cookie yet, or it expired) is just "not logged in,"
  // not an error to show the cashier.
  useEffect(() => {
    (async () => {
      try {
        const { access } = await posApi.refreshSilent();
        applyAccessToken(access);
      } catch {
        // no session to restore — normal, land on the sign-in screen
      } finally {
        setRestoring(false);
      }
    })();
  }, []);

  async function handleLogin(e) {
    e.preventDefault();
    setLoginError("");
    try {
      const { access } = await posApi.login(username, password);
      applyAccessToken(access);
      await loadProducts();
    } catch (err) {
      // Owner/Manager accounts with a confirmed TOTP device get a 401 here
      // with mfa_required: true instead of tokens — a cashier login never
      // hits this branch. Enrollment itself stays admin-app only; this
      // just lets an already-enrolled account complete a till login.
      if (err.data?.mfa_required) {
        setMfaRequired(true);
        setLoginError("");
      } else {
        setLoginError(err.message);
      }
    }
  }

  async function handleMfaSubmit(e) {
    e.preventDefault();
    setLoginError("");
    try {
      const { access } = await posApi.loginWithMfa(username, password, mfaCode);
      applyAccessToken(access);
      await loadProducts();
    } catch (err) {
      setLoginError(err.message);
    }
  }

  async function loadProducts(q = "") {
    try {
      const data = await posApi.searchProducts(q);
      setProducts(data);
    } catch (err) {
      setCheckoutError(err.message);
    }
  }

  useEffect(() => {
    if (!role) return;
    const timeout = setTimeout(() => loadProducts(query), 200); // debounce search
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, role]);

  function addToCart(product) {
    setCart((prev) => {
      const existing = prev.find((line) => line.product.id === product.id);
      if (existing) {
        return prev.map((line) =>
          line.product.id === product.id ? { ...line, quantity: line.quantity + 1 } : line
        );
      }
      return [...prev, { product, quantity: 1 }];
    });
  }

  function changeQuantity(productId, delta) {
    setCart((prev) =>
      prev
        .map((line) => (line.product.id === productId ? { ...line, quantity: line.quantity + delta } : line))
        .filter((line) => line.quantity > 0)
    );
  }

  const total = useMemo(
    () => cart.reduce((sum, line) => sum + Number(line.product.unit_price) * line.quantity, 0),
    [cart]
  );

  async function completeSale() {
    setCheckoutError("");
    setSubmitting(true);
    try {
      const result = await posApi.checkout({
        idempotency_key: idempotencyKey,
        payment_method: paymentMethod,
        items: cart.map((line) => ({ product_id: line.product.id, quantity: line.quantity })),
      });
      setReceipt(result);
      setCart([]);
      setIdempotencyKey(newIdempotencyKey()); // fresh key for the NEXT sale only
      await loadProducts(query); // refresh stock levels shown on tiles
    } catch (err) {
      // Same idempotencyKey is deliberately KEPT on failure — if the
      // cashier retries, it's treated as the same attempt, not a new sale.
      setCheckoutError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogout() {
    try {
      await posApi.logout(); // blacklists the refresh token and clears its cookie server-side
    } catch {
      // Even if this fails (e.g. already expired), still clear client state
      // below — the cashier's goal is to end up logged out either way.
    }
    clearAccessToken();
    setRole(null);
    setCart([]);
    setProducts([]);
    setMfaRequired(false);
    setMfaCode("");
    setReceipt(null);
    setShowReceipt(false);
  }

  if (restoring) {
    return <div className="pos-root" />;
  }

  if (!role) {
    return (
      <div className="pos-root">
        {!mfaRequired ? (
          <form className="pos-login" onSubmit={handleLogin}>
            <p className="eyebrow">Till sign-in</p>
            <h1>Start your shift</h1>
            <div className="pos-field">
              <label htmlFor="username">Username</label>
              <input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
            </div>
            <div className="pos-field">
              <label htmlFor="password">Password</label>
              <input
                id="password" type="password" value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <button className="pos-button-primary" type="submit">Sign in</button>
            {loginError && <p className="pos-error">{loginError}</p>}
          </form>
        ) : (
          <form className="pos-login" onSubmit={handleMfaSubmit}>
            <p className="eyebrow">Two-factor required</p>
            <h1>Enter your code</h1>
            <div className="pos-field">
              <label htmlFor="mfa-code">6-digit code</label>
              <input
                id="mfa-code"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="123456"
                inputMode="numeric"
                autoFocus
                style={{ fontSize: "1.2rem", letterSpacing: "0.3em", textAlign: "center" }}
              />
            </div>
            <button className="pos-button-primary" type="submit" disabled={mfaCode.length !== 6}>
              Verify and sign in
            </button>
            <button
              type="button"
              className="pos-button-secondary"
              onClick={() => { setMfaRequired(false); setMfaCode(""); setLoginError(""); }}
            >
              Back
            </button>
            {loginError && <p className="pos-error">{loginError}</p>}
          </form>
        )}
      </div>
    );
  }

  if (receipt) {
    return (
      <div className="pos-root">
        <div className="pos-confirmation">
          <span className="stamp">SALE COMPLETE</span>
          <h2>Total: {Number(receipt.total_amount).toFixed(2)}</h2>
          <p>{receipt.items.length} item(s) · {receipt.payment_method}</p>
          <button className="pos-button-secondary" style={{ marginTop: 16 }} onClick={() => setShowReceipt(true)}>
            View / print receipt
          </button>
          <button
            className="pos-button-primary"
            style={{ marginTop: 8 }}
            onClick={() => { setReceipt(null); setShowReceipt(false); }}
          >
            New sale
          </button>
        </div>
        {showReceipt && <Receipt sale={receipt} onClose={() => setShowReceipt(false)} />}
      </div>
    );
  }

  return (
    <div className="pos-root">
      <div className="pos-header">
        <div>
          <h1>Mini Supermarket — Till</h1>
          <span className="till-id">role: {role}</span>
        </div>
        <button className="pos-logout" onClick={handleLogout}>Log out</button>
      </div>

      <div className="pos-main">
        <div className="pos-catalog">
          <input
            className="pos-search"
            placeholder="Search or scan a barcode…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <div className="pos-grid">
            {products.map((product) => (
              <button key={product.id} className="pos-tile" onClick={() => addToCart(product)}>
                <span className="tile-name">{product.name}</span>
                <span className="tile-price">{Number(product.unit_price).toFixed(2)}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="pos-receipt-panel">
          <div className="pos-receipt-tape">
            <div className="pos-receipt-items">
              {cart.length === 0 && <p className="pos-receipt-empty">Scan or tap a product to begin</p>}
              {cart.map((line) => (
                <div className="pos-line-item" key={line.product.id}>
                  <span className="line-name">{line.product.name}</span>
                  <span className="line-dots" />
                  <span className="line-qty-controls">
                    <button onClick={() => changeQuantity(line.product.id, -1)} aria-label="Decrease quantity">−</button>
                    {line.quantity}
                    <button onClick={() => changeQuantity(line.product.id, 1)} aria-label="Increase quantity">+</button>
                  </span>
                  <span className="line-price">
                    {(Number(line.product.unit_price) * line.quantity).toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
            <div className="pos-receipt-total">
              <span className="label">Total</span>
              <span className="amount">{total.toFixed(2)}</span>
            </div>
          </div>

          <div className="pos-payment-row">
            {["CASH", "MOMO"].map((method) => (
              <button
                key={method}
                className="pos-payment-option"
                data-active={paymentMethod === method}
                onClick={() => setPaymentMethod(method)}
              >
                {method === "CASH" ? "Cash" : "Mobile Money"}
              </button>
            ))}
          </div>

          {checkoutError && <p className="pos-toast-error">{checkoutError}</p>}

          <button
            className="pos-complete-sale"
            disabled={cart.length === 0 || submitting}
            onClick={completeSale}
          >
            {submitting ? "Processing…" : "Complete sale"}
          </button>
        </div>
      </div>
    </div>
  );
}
