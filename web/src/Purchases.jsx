import { useEffect, useState } from "react";
import { api } from "./api";

export default function Purchases() {
  const [payload, setPayload] = useState(null);
  const [status, setStatus] = useState("Loading your purchases…");

  async function load() {
    try {
      const next = await api("/purchases");
      setPayload(next);
      setStatus("");
    } catch (error) {
      setStatus(error.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function markReturned(orderId) {
    await api("/purchases/return", { method: "POST", body: { order_id: orderId } });
    load();
  }

  const orders = (payload && payload.orders) || [];
  const taste = (payload && payload.taste) || {};
  const kept = [].concat(taste.brands || [], taste.colors || []).filter(Boolean);
  const update = payload && payload.update;

  return (
    <section className="panel">
      <p className="kicker">After you buy</p>
      <h1>Your products</h1>
      {update && update.text ? <p>{update.text}</p> : null}
      <p className="quiet">
        {kept.length ? "Similar products use what you kept: " + kept.join(", ") + "." : "A checkout or a past bill adds the brands and colors used for similar products."}
        {taste.avoid && taste.avoid.length ? " Returned brands are left out: " + taste.avoid.join(", ") + "." : ""}
      </p>
      {status ? <p className="quiet">{status}</p> : null}
      <div className="cards">
        {orders.length ? (
          orders.map((order) => {
            const returned = String(order.status || "") === "Returned" || /returned:yes/.test(String(order.materials || ""));
            return (
              <article className="card" key={order.orderId || order.name}>
                <h2>{order.name}</h2>
                <p>
                  {order.store || "Store"} · ${order.price || ""}
                </p>
                <p>
                  <strong>{order.status || "Placed"}</strong>
                  {order.statusNote ? " — " + order.statusNote : ""}
                </p>
                {returned ? null : (
                  <button className="btn" type="button" onClick={() => markReturned(order.orderId)}>
                    Mark returned
                  </button>
                )}
              </article>
            );
          })
        ) : (
          <p>No purchases yet. Finish a store checkout with the extension, or choose Purchase all in the page chat.</p>
        )}
      </div>
    </section>
  );
}
