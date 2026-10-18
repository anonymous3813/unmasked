/* Receive analysis notices and pin them to the open product page. */
if (window.UnmaskedOverlay) window.UnmaskedOverlay.mountChat();

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "unmasked-shadow" || !window.UnmaskedOverlay) return;
  const notes = Array.isArray(message.notes) ? message.notes : [];
  window.UnmaskedOverlay.show(notes);
  sendResponse({ shown: notes.length });
});
