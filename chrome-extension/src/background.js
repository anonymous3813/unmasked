/* Ask the local shop API for marks, then hand them to the product page. */

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message) return;
  if (message.type === "unmasked-ask") {
    fetch("http://127.0.0.1:8000/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: message.question || "",
        url: message.url,
        title: message.title || "",
        page_text: message.pageText || "",
        notes: Array.isArray(message.notes) ? message.notes : [],
        visits: Array.isArray(message.visits) ? message.visits : [],
        dossier: message.dossier || {},
        outside: message.outside || {},
        product_page: Boolean(message.productPage),
      }),
    })
      .then((response) => response.json())
      .then((payload) => sendResponse(payload))
      .catch(() => sendResponse({ answer: "I couldn't reach the agent just now." }));
    return true;
  }
  if (message.type === "unmasked-inbox") {
    fetch("http://127.0.0.1:8000/inbox")
      .then((response) => response.json())
      .then((payload) => sendResponse(payload))
      .catch(() => sendResponse({ messages: [], calls: [], orders: [] }));
    return true;
  }
  if (message.type === "unmasked-inbox-send") {
    fetch("http://127.0.0.1:8000/inbox/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: message.text || "",
        cart: Array.isArray(message.cart) ? message.cart : [],
        notes: Array.isArray(message.notes) ? message.notes : [],
      }),
    })
      .then((response) => response.json())
      .then((payload) => sendResponse(payload))
      .catch(() => sendResponse({ answer: "I couldn't reach the assistant." }));
    return true;
  }
  if (message.type === "unmasked-call") {
    fetch("http://127.0.0.1:8000/inbox/call", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cart: Array.isArray(message.cart) ? message.cart : [],
        notes: Array.isArray(message.notes) ? message.notes : [],
      }),
    })
      .then((response) => response.json())
      .then((payload) => sendResponse(payload))
      .catch(() => sendResponse({ summary: "The assistant didn't pick up." }));
    return true;
  }
  if (message.type === "unmasked-assistant") {
    fetch("http://127.0.0.1:8000/assistant")
      .then((response) => response.json())
      .then((payload) => sendResponse(payload))
      .catch(() => sendResponse({ name: "Your Online Assistant", phone: "", phoneDisplay: "" }));
    return true;
  }
  if (message.type === "unmasked-checkout") {
    fetch("http://127.0.0.1:8000/cart/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: Array.isArray(message.items) ? message.items : [] }),
    })
      .then((response) => response.json())
      .then((payload) => sendResponse(payload))
      .catch(() => sendResponse({ answer: "I couldn't save those orders just now.", orders: [] }));
    return true;
  }
  if (message.type === "unmasked-tax") {
    fetch("http://127.0.0.1:8000/sales-tax", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amount: message.amount || "",
        postal_code: message.postalCode || "",
      }),
    })
      .then((response) => response.json())
      .then((payload) => sendResponse(payload))
      .catch(() => sendResponse({ note: null }));
    return true;
  }
  if (message.type === "unmasked-intro") {
    fetch("http://127.0.0.1:8000/intro", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: message.text || "" }),
    })
      .then((response) => response.json())
      .then((payload) => sendResponse(payload))
      .catch(() => sendResponse({ sent: false }));
    return true;
  }
  if (message.type === "unmasked-wishlist") {
    fetch("http://127.0.0.1:8000/wishlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: message.name || "",
        url: message.url || "",
        store: message.store || "",
        price: message.price || "",
        imageUrl: message.imageUrl || "",
        environmentScore: message.environmentScore == null ? null : message.environmentScore,
      }),
    })
      .then((response) => response.json())
      .then((payload) => sendResponse(payload))
      .catch(() => sendResponse({ saved: false, answer: "I couldn't save that to the wishlist." }));
    return true;
  }
  if (message.type === "unmasked-alternatives") {
    fetch("http://127.0.0.1:8000/alternatives", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: message.name || "",
        url: message.url || "",
        page_text: message.pageText || "",
        listed_price: message.listedPrice || null,
      }),
    })
      .then((response) => response.json())
      .then((payload) => sendResponse(payload))
      .catch(() => sendResponse({ products: [] }));
    return true;
  }
  if (message.type !== "unmasked-analyze") return;
  const tabId = sender.tab && sender.tab.id;
  fetch("http://127.0.0.1:8000/page-notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: message.url,
      listed_price: message.listedPrice || null,
      postal_code: message.postalCode || null,
      page_text: message.pageText || "",
      record: message.record || {},
      product_page: Boolean(message.productPage),
    }),
  })
    .then((response) => response.json())
    .then((payload) => {
      if (tabId != null) {
        chrome.tabs.sendMessage(tabId, {
          type: "unmasked-shadow",
          notes: payload.notes || [],
          visits: payload.visits || [],
          dossier: payload.dossier || null,
          outside: payload.outside || null,
          report: payload.report || null,
          active: payload.active !== false,
        });
      }
      sendResponse(payload);
    })
    .catch(() => sendResponse({ notes: [], visits: [] }));
  return true;
});
