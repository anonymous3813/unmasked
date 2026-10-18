/* Pin price and policy marks on the open product page, and keep the chat there. */
if (window.UnmaskedOverlay) window.UnmaskedOverlay.mountChat();

function listedPrice() {
  if (!document.body) return "";
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let best = null;
  let node = walker.nextNode();
  while (node) {
    const match = (node.nodeValue || "").match(/\$\s?(\d+(?:,\d{3})*(?:\.\d{2})?)/);
    const parent = node.parentElement;
    if (match && parent) {
      const style = getComputedStyle(parent);
      const rect = parent.getBoundingClientRect();
      const size = parseFloat(style.fontSize) || 0;
      const shown =
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        rect.width > 1 &&
        rect.height > 1 &&
        rect.bottom > 0 &&
        rect.top < window.innerHeight;
      if (shown && (!best || size > best.size)) best = { amount: match[1].replace(/,/g, ""), size };
    }
    node = walker.nextNode();
  }
  return best ? best.amount : "";
}

let apiShown = false;
let localShown = false;
let requested = false;

function localPriceNote() {
  const amount = listedPrice();
  if (!amount) return [];
  const listed = Number(amount).toFixed(2);
  return [
    {
      kind: "price",
      title: "Price with tax",
      message:
        "The page shows USD " +
        listed +
        ". That price does not include tax, so the checkout total will be higher.",
      listedPrice: listed,
    },
  ];
}

function applyResult(payload) {
  if (!payload || !window.UnmaskedOverlay) return;
  const notes = Array.isArray(payload.notes) ? payload.notes : [];
  const visits = Array.isArray(payload.visits) ? payload.visits : [];
  if (notes.length) {
    apiShown = true;
    window.UnmaskedOverlay.show(notes);
  }
  if (visits.length && window.UnmaskedOverlay.showSources) window.UnmaskedOverlay.showSources(visits);
}

function showLocalMarks() {
  if (apiShown || localShown || !window.UnmaskedOverlay) return;
  const notes = localPriceNote();
  if (!notes.length) return;
  localShown = true;
  window.UnmaskedOverlay.show(notes);
}

function requestNotes() {
  if (requested || !document.body || !/\$\s?\d/.test(document.body.innerText || "")) return;
  requested = true;
  chrome.runtime.sendMessage(
    { type: "unmasked-analyze", url: location.href, listedPrice: listedPrice() },
    (response) => {
      if (chrome.runtime.lastError) return;
      applyResult(response);
    }
  );
}

showLocalMarks();
requestNotes();

const watcher = new MutationObserver(() => {
  showLocalMarks();
  requestNotes();
});
if (document.documentElement) {
  watcher.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || !window.UnmaskedOverlay) return;
  if (message.type === "unmasked-refresh") {
    requested = false;
    requestNotes();
    sendResponse({ ok: true });
    return;
  }
  if (message.type !== "unmasked-shadow") return;
  applyResult(message);
  sendResponse({ shown: Array.isArray(message.notes) ? message.notes.length : 0 });
});
