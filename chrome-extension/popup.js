document
  .getElementById("analyze")
  .addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true
    });

    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        title: document.title,
        url: location.href,
        text: document.body.innerText.slice(0, 5000)
      })
    });

    console.log(result);
    const notes = Array.isArray(result.notes) ? result.notes : [];
    if (notes.length) {
      await chrome.tabs.sendMessage(tab.id, { type: "unmasked-shadow", notes });
    }
  });
