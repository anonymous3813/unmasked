/* Ask the shop API for marks, then hand them to the product page. */

const API = "https://unmasked.fastapicloud.dev";

function callApi(path, body) {
  return new Promise((resolve) => {
    chrome.storage.local.get({ unmaskedToken: "" }, (data) => {
      const headers = { "Content-Type": "application/json" };
      if (data.unmaskedToken) headers.Authorization = "Bearer " + data.unmaskedToken;
      const options = { method: body ? "POST" : "GET", headers };
      if (body) options.body = JSON.stringify(body);
      fetch(API + path, options)
        .then(async (response) => {
          const payload = await response.json().catch(() => ({}));
          if (response.status === 401) payload.detail = payload.detail || "Sign in to use Unmasked.";
          resolve(payload);
        })
        .catch(() => resolve(null));
    });
  });
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message) return;
  if (message.type === "unmasked-session") {
    chrome.storage.local.get({ unmaskedToken: "", unmaskedAccount: null }, (data) => {
      sendResponse({ token: data.unmaskedToken || "", account: data.unmaskedAccount });
    });
    return true;
  }
  if (message.type === "unmasked-logout") {
    chrome.storage.local.remove(["unmaskedToken", "unmaskedAccount"], () => sendResponse({ signedOut: true }));
    return true;
  }
  if (message.type === "unmasked-auth") {
    const path = message.mode === "register" ? "/auth/register" : "/auth/login";
    fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: message.email || "", password: message.password || "", name: message.name || "", phone: message.phone || "" }),
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.token) {
          sendResponse({ detail: payload.detail || "That email or password is not right." });
          return;
        }
        chrome.storage.local.set({ unmaskedToken: payload.token, unmaskedAccount: payload.account }, () => sendResponse(payload));
      })
      .catch(() => sendResponse({ detail: "Sign-in could not reach the account service." }));
    return true;
  }
  if (message.type === "unmasked-ask") {
    callApi("/ask", {
      question: message.question || "",
      url: message.url,
      title: message.title || "",
      page_text: message.pageText || "",
      notes: Array.isArray(message.notes) ? message.notes : [],
      visits: Array.isArray(message.visits) ? message.visits : [],
      dossier: message.dossier || {},
      outside: message.outside || {},
      product_page: Boolean(message.productPage),
    }).then((payload) => sendResponse(payload || { answer: "I couldn't reach the agent just now." }));
    return true;
  }
  if (message.type === "unmasked-inbox") {
    callApi("/inbox").then((payload) => sendResponse(payload || { messages: [], calls: [], orders: [] }));
    return true;
  }
  if (message.type === "unmasked-inbox-send") {
    callApi("/inbox/message", {
      text: message.text || "",
      cart: Array.isArray(message.cart) ? message.cart : [],
      notes: Array.isArray(message.notes) ? message.notes : [],
    }).then((payload) => sendResponse(payload || { answer: "I couldn't reach the assistant." }));
    return true;
  }
  if (message.type === "unmasked-call") {
    callApi("/inbox/call", {
      cart: Array.isArray(message.cart) ? message.cart : [],
      notes: Array.isArray(message.notes) ? message.notes : [],
    }).then((payload) => sendResponse(payload || { summary: "The assistant didn't pick up." }));
    return true;
  }
  if (message.type === "unmasked-assistant") {
    callApi("/assistant").then((payload) => sendResponse(payload || { name: "Your Online Assistant", phone: "", phoneDisplay: "" }));
    return true;
  }
  if (message.type === "unmasked-checkout") {
    callApi("/cart/checkout", { items: Array.isArray(message.items) ? message.items : [] }).then((payload) =>
      sendResponse(payload || { answer: "I couldn't save those orders just now.", orders: [] })
    );
    return true;
  }
  if (message.type === "unmasked-tax") {
    callApi("/sales-tax", { amount: message.amount || "", postal_code: message.postalCode || "" }).then((payload) =>
      sendResponse(payload || { note: null })
    );
    return true;
  }
  if (message.type === "unmasked-intro") {
    callApi("/intro", { text: message.text || "" }).then((payload) => sendResponse(payload || { sent: false }));
    return true;
  }
  if (message.type === "unmasked-wishlist") {
    callApi("/wishlist", {
      name: message.name || "",
      url: message.url || "",
      store: message.store || "",
      price: message.price || "",
      imageUrl: message.imageUrl || "",
      environmentScore: message.environmentScore == null ? null : message.environmentScore,
    }).then((payload) => sendResponse(payload || { saved: false, answer: "I couldn't save that to the wishlist." }));
    return true;
  }
  if (message.type === "unmasked-alternatives") {
    callApi("/alternatives", {
      name: message.name || "",
      url: message.url || "",
      page_text: message.pageText || "",
      listed_price: message.listedPrice || null,
    }).then((payload) => sendResponse(payload || { products: [] }));
    return true;
  }
  if (message.type !== "unmasked-analyze") return;
  const tabId = sender.tab && sender.tab.id;
  callApi("/page-notes", {
    url: message.url,
    listed_price: message.listedPrice || null,
    postal_code: message.postalCode || null,
    page_text: message.pageText || "",
    record: message.record || {},
    product_page: Boolean(message.productPage),
  }).then((payload) => {
    const result = payload || { notes: [], visits: [] };
    if (tabId != null) {
      chrome.tabs.sendMessage(tabId, {
        type: "unmasked-shadow",
        notes: result.notes || [],
        visits: result.visits || [],
        dossier: result.dossier || null,
        outside: result.outside || null,
        report: result.report || null,
        footprint: result.footprint || null,
        registry: result.registry || [],
        active: result.active !== false,
      });
    }
    sendResponse(result);
  });
  return true;
});
