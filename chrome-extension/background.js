/* Ask the local shop API for marks, then hand them to the product page. */

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "unmasked-analyze") return;
  const tabId = sender.tab && sender.tab.id;
  fetch("http://127.0.0.1:8000/page-notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: message.url,
      listed_price: message.listedPrice || null,
    }),
  })
    .then((response) => response.json())
    .then((payload) => {
      if (tabId != null) {
        chrome.tabs.sendMessage(tabId, {
          type: "unmasked-shadow",
          notes: payload.notes || [],
          visits: payload.visits || [],
        });
      }
      sendResponse(payload);
    })
    .catch(() => sendResponse({ notes: [], visits: [] }));
  return true;
});
