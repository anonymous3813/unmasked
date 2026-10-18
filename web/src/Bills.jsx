import { useEffect, useState } from "react";
import { api } from "./api";

export default function Bills() {
  const [file, setFile] = useState(null);
  const [drag, setDrag] = useState(false);
  const [status, setStatus] = useState("");
  const [receipts, setReceipts] = useState([]);

  async function load() {
    const payload = await api("/purchases");
    setReceipts(payload.receipts || []);
  }

  useEffect(() => {
    load().catch((error) => setStatus(error.message));
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (!file) {
      setStatus("Choose a bill file first.");
      return;
    }
    setStatus("Reading the bill…");
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    bytes.forEach((value) => {
      binary += String.fromCharCode(value);
    });
    const body = { text: "", filename: file.name, data_base64: btoa(binary) };
    try {
      const payload = await api("/receipts", { method: "POST", body });
      const count = Array.isArray(payload.items) ? payload.items.length : 0;
      setStatus(payload.reason || (count ? "Read " + count + " product" + (count === 1 ? "" : "s") + " from this bill." : "No product line was read."));
      setFile(null);
      await load();
    } catch (error) {
      setStatus(error.message || "The bill could not be read just now.");
    }
  }

  return (
    <section className="panel">
      <p className="kicker">Past bills</p>
      <h1>Add a bill</h1>
      <p className="quiet">Drop a photo, PDF, or text file. Brands and colors from the bill are used for similar products.</p>
      <form className="bill" onSubmit={submit}>
        <label
          className={"drop" + (drag ? " over" : "")}
          onDragOver={(event) => {
            event.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDrag(false);
            const next = event.dataTransfer.files && event.dataTransfer.files[0];
            if (next) setFile(next);
          }}
        >
          <input
            type="file"
            accept=".txt,.pdf,.png,.jpg,.jpeg,.webp,text/plain,application/pdf,image/*"
            onChange={(event) => setFile(event.target.files[0] || null)}
          />
          <span>{file ? file.name : "Drop a bill here, or choose a file"}</span>
        </label>
        <button className="btn fill" type="submit">
          Read this bill
        </button>
      </form>
      {status ? <p>{status}</p> : null}
      <div className="cards">
        {receipts.map((receipt) => (
          <article className="card" key={(receipt.filename || "bill") + (receipt.savedAt || "")}>
            <h2>{receipt.filename || "Receipt"}</h2>
            <div className="chips">
              {(receipt.items || []).length ? (
                receipt.items.map((item) => (
                  <span key={item.name + (item.brand || "")}>
                    {item.name}
                    {item.brand ? " · " + item.brand : ""}
                    {item.color ? " · " + item.color : ""}
                    {item.returned ? " · returned" : ""}
                  </span>
                ))
              ) : (
                <span>No product line was read.</span>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
