import { useEffect, useState } from "react";
import { api } from "./api";

export default function Wishlist() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("Loading your wishlist…");

  useEffect(() => {
    api("/wishlist")
      .then((payload) => {
        setItems(payload.items || []);
        setStatus("");
      })
      .catch((error) => setStatus(error.message));
  }, []);

  return (
    <section className="panel">
      <p className="kicker">Saved from the agent</p>
      <h1>Wishlist</h1>
      <p className="quiet">Products you save from the page chat are listed here.</p>
      {status ? <p className="quiet">{status}</p> : null}
      <div className="cards">
        {items.length ? (
          items.map((item) => (
            <article className="card" key={item.url}>
              <h2>{item.name}</h2>
              <p>
                {item.store || "Store"}
                {item.price ? " · $" + item.price : ""}
              </p>
              {item.url ? <a href={item.url}>Open the product</a> : null}
            </article>
          ))
        ) : (
          <p>No saved products yet. Choose Wishlist on a recommended product in the page chat.</p>
        )}
      </div>
    </section>
  );
}
