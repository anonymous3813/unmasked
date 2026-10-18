/* On-page marks for prices, policies, and better-product notices. */
(function () {
  const HOST_ID = "unmasked-root";
  const CHAT_ID = "unmasked-chat";
  const KEYWORDS = {
    "return limit": ["return policy", "returns", "return"],
    "restocking fee": ["restocking", "restock", "returns", "return"],
    "cancellation terms": ["cancellation", "cancel"],
    "warranty exclusion": ["warranty", "guarantee"],
    "damage policy": ["damage"],
    availability: ["in stock", "out of stock", "ships in", "only"],
  };

  let marks = [];
  let frame = 0;
  let currentNotes = [];

  function show(notes) {
    currentNotes = Array.isArray(notes) ? notes : [];
    clear();
    if (!currentNotes.length || !document.body) return;
    const shadow = host().shadowRoot;
    currentNotes.forEach((note) => mount(shadow, note));
    layout();
    window.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);
  }

  function clear() {
    window.removeEventListener("scroll", schedule, true);
    window.removeEventListener("resize", schedule);
    marks = [];
    const existing = document.getElementById(HOST_ID);
    if (existing) existing.remove();
  }

  function mountChat() {
    if (document.getElementById(CHAT_ID) || !document.body) return;
    const element = document.createElement("div");
    element.id = CHAT_ID;
    element.style.cssText = "position:fixed;inset:0;z-index:2147483647;pointer-events:none";
    const shadow = element.attachShadow({ mode: "open" });
    shadow.appendChild(chatStyle());
    shadow.appendChild(chatDock());
    document.documentElement.appendChild(element);
  }

  function host() {
    const element = document.createElement("div");
    element.id = HOST_ID;
    element.style.cssText = [
      "position:fixed",
      "inset:0",
      "z-index:2147483646",
      "pointer-events:none",
    ].join(";");
    element.attachShadow({ mode: "open" });
    element.shadowRoot.appendChild(style());
    document.documentElement.appendChild(element);
    return element;
  }

  function mount(shadow, note) {
    const anchor = findAnchor(note);
    if (!anchor) return;
    const prices = note.kind === "price" ? readPrices(note) : null;
    const slash = prices ? drawSlash(shadow) : null;
    const chip = note.kind === "recommendation" ? drawListing(note) : drawChip(note, prices);
    shadow.appendChild(chip);
    marks.push({ anchor, chip, slash, listing: note.kind === "recommendation" });
  }

  function findAnchor(note) {
    if (note.kind === "price") {
      return findPrice(readPrices(note).listed) || decisionPoint();
    }
    if (note.kind === "recommendation") return findProblem(note);
    const words = KEYWORDS[(note.title || "").toLowerCase()] || [];
    return findPhrase(words) || findPrice(readPrices(note).listed) || decisionPoint();
  }

  function findProblem(note) {
    const aspect = String(note.aspect || "cost_value").toLowerCase();
    if (aspect === "environmental") {
      return (
        findPhrase(["recycled", "sustainable", "organic", "environment", "material"]) ||
        findProminentPrice()
      );
    }
    if (aspect === "durability") {
      return findPhrase(["waterproof", "lifetime", "guaranteed", "warranty", "durable"]) || findProminentPrice();
    }
    return findProminentPrice();
  }

  function findProminentPrice() {
    return bestMatch(/\$(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?/);
  }

  function findPrice(listed) {
    if (!listed) return null;
    const whole = String(Math.round(Number(listed)));
    const pattern = new RegExp(
      "(?:\\$|USD\\s*)" + whole + "(?:\\.00)?(?!\\d)",
      "i"
    );
    return bestMatch(pattern);
  }

  function findPhrase(words) {
    if (!words.length) return null;
    const pattern = new RegExp(
      words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"),
      "i"
    );
    return bestMatch(pattern);
  }

  function bestMatch(pattern) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let best = null;
    let node = walker.nextNode();
    while (node) {
      const text = node.nodeValue || "";
      const parent = node.parentElement;
      if (pattern.test(text) && parent && usable(parent)) {
        const size = parseFloat(getComputedStyle(parent).fontSize) || 0;
        const length = parent.innerText.trim().length;
        const score = size * 1000 - length;
        if (!best || score > best.score) best = { element: parent, score };
      }
      node = walker.nextNode();
    }
    return best ? { element: best.element, pattern } : null;
  }

  function usable(element) {
    const tag = element.tagName;
    if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT" || tag === "TEXTAREA") {
      return false;
    }
    if (element.closest("#" + HOST_ID)) return false;
    const text = element.innerText.trim();
    return text.length > 0 && text.length < 220;
  }

  function decisionPoint() {
    const pattern = /add to cart|buy now|buy/i;
    const button = Array.from(document.querySelectorAll("button, a")).find((element) =>
      pattern.test(element.innerText)
    );
    if (button) return { element: button, pattern };
    const title = document.querySelector("h1");
    return title ? { element: title, pattern: /\S[\s\S]*\S|\S/ } : null;
  }

  function readPrices(note) {
    const listed = note.listedPrice || firstAmount(note.message, /(?:USD|\$)\s*([\d,]+\.\d{2})/i);
    const withTax =
      note.priceWithTax ||
      firstAmount(note.message, /with tax, the price is (?:USD|\$)\s*([\d,]+\.\d{2})/i);
    return { listed, withTax };
  }

  function firstAmount(text, pattern) {
    const match = String(text || "").match(pattern);
    return match ? match[1].replace(/,/g, "") : "";
  }

  function drawSlash(shadow) {
    const slash = document.createElement("div");
    slash.className = "slash";
    slash.setAttribute("aria-hidden", "true");
    slash.innerHTML =
      '<svg viewBox="0 0 100 100" preserveAspectRatio="none">' +
      '<line x1="2" y1="88" x2="98" y2="12" />' +
      "</svg>";
    shadow.appendChild(slash);
    return slash;
  }

  function drawListing(note) {
    const chip = document.createElement("article");
    chip.className = "chip listing";
    const link = document.createElement("a");
    link.className = "listing-link";
    link.href = note.productUrl || note.product_url || "";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    const image = document.createElement("img");
    image.src = note.imageUrl || note.image_url || "";
    image.alt = "";
    const name = document.createElement("span");
    name.className = "listing-name";
    name.textContent = note.productName || note.title || "";
    const price = document.createElement("span");
    price.className = "listing-price";
    price.textContent = formatPrice(note.price);
    link.append(image, name, price);
    const reason = document.createElement("p");
    reason.className = "listing-reason";
    reason.textContent = note.message || note.reason || "";
    chip.append(link, reason);
    return chip;
  }

  function formatPrice(value) {
    const text = String(value || "").trim();
    if (!text) return "";
    if (text.charAt(0) === "$") return text;
    const amount = Number(text.replace(/,/g, ""));
    return Number.isFinite(amount) ? "$" + amount.toFixed(2) : text;
  }

  function drawChip(note, prices) {
    const chip = document.createElement("div");
    chip.className = "chip";
    const lead = firstSentence(note.message);
    const label = prices && prices.withTax ? "Price with tax: $" + prices.withTax : lead;
    const more = label !== note.message;
    chip.innerHTML =
      '<button type="button" class="label"></button>' +
      '<div class="card" hidden><p></p><button type="button" class="close">Close</button></div>';
    chip.querySelector(".label").textContent = label;
    chip.querySelector(".card p").textContent = note.message;
    const button = chip.querySelector(".label");
    const card = chip.querySelector(".card");
    button.setAttribute("aria-expanded", "false");
    if (!more) button.disabled = true;
    button.addEventListener("click", () => toggle(chip, button, card));
    chip.querySelector(".close").addEventListener("click", () => toggle(chip, button, card));
    return chip;
  }

  function firstSentence(message) {
    const text = String(message || "").trim();
    const match = text.match(/^.*?[.!?](?:\s|$)/);
    return match ? match[0].trim() : text;
  }

  function toggle(chip, button, card) {
    const open = card.hidden;
    card.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
    chip.classList.toggle("open", open);
    layout();
  }

  function schedule() {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      layout();
    });
  }

  function layout() {
    const used = [];
    const ordered = marks
      .filter((mark) => !mark.listing)
      .concat(marks.filter((mark) => mark.listing));
    ordered.forEach((mark) => {
      const rect = textBox(mark.anchor);
      const onScreen =
        rect.width > 0 &&
        rect.bottom > 0 &&
        rect.top < window.innerHeight &&
        rect.right > 0 &&
        rect.left < window.innerWidth;
      mark.chip.hidden = !onScreen;
      if (mark.slash) mark.slash.hidden = !onScreen;
      if (!onScreen) return;
      if (mark.slash) {
        mark.slash.style.left = rect.left + "px";
        mark.slash.style.top = rect.top + "px";
        mark.slash.style.width = rect.width + "px";
        mark.slash.style.height = rect.height + "px";
      }
      const spot = beside(
        clearance(mark.anchor, rect),
        mark.chip,
        used,
        mark.listing ? textObstacles(mark.anchor) : []
      );
      mark.chip.style.left = spot.left + "px";
      mark.chip.style.top = spot.top + "px";
    });
  }

  function textBox(anchor) {
    const node = textNode(anchor.element, anchor.pattern);
    const value = node ? node.nodeValue || "" : "";
    const match = node ? value.match(anchor.pattern) : null;
    if (!node || !match) return anchor.element.getBoundingClientRect();
    const range = document.createRange();
    range.setStart(node, match.index);
    range.setEnd(node, match.index + match[0].length);
    const rect = range.getBoundingClientRect();
    return rect.width > 0 ? rect : anchor.element.getBoundingClientRect();
  }

  function textNode(element, pattern) {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      if (pattern.test(node.nodeValue || "")) return node;
      node = walker.nextNode();
    }
    return null;
  }

  function clearance(anchor, text) {
    const block = anchor.element.getBoundingClientRect();
    if (block.width <= text.width + 48 && block.height <= text.height + 32) return block;
    return text;
  }

  function textObstacles(anchor) {
    const boxes = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const parent = node.parentElement;
      if (parent && usable(parent) && !anchor.element.contains(parent)) {
        const range = document.createRange();
        range.selectNodeContents(node);
        const rect = range.getBoundingClientRect();
        if (rect.width > 2 && rect.height > 2) boxes.push(rect);
      }
      node = walker.nextNode();
    }
    document.querySelectorAll("button, a").forEach((element) => {
      if (element === anchor.element || anchor.element.contains(element)) return;
      const rect = element.getBoundingClientRect();
      if (rect.width > 2 && rect.height > 2) boxes.push(rect);
    });
    return boxes;
  }

  function beside(rect, chip, used, obstacles) {
    const width = chip.offsetWidth || 220;
    const height = chip.offsetHeight || 36;
    const gap = 8;
    let left = rect.right + gap;
    let top = rect.top;
    if (left + width > window.innerWidth - 12) {
      left = Math.max(12, rect.left);
      top = rect.bottom + gap;
    }
    const blocked = used.concat(obstacles || []);
    for (let guard = 0; guard < 8; guard += 1) {
      const hit = blocked.find(
        (box) =>
          left < box.right &&
          left + width > box.left &&
          top < box.bottom &&
          top + height > box.top
      );
      if (!hit) break;
      top = hit.bottom + gap;
    }
    used.push({ left, top, right: left + width, bottom: top + height });
    return { left, top };
  }

  function style() {
    const element = document.createElement("style");
    element.textContent = [
      ".slash { position: fixed; pointer-events: none; }",
      ".slash svg { width: 100%; height: 100%; overflow: visible; }",
      ".slash line { stroke: #9f2d20; stroke-width: 3; stroke-linecap: round; }",
      ".chip { position: fixed; width: max-content; max-width: 260px; pointer-events: auto;",
      "font-family: Palatino, Georgia, serif; color: #1c1917; }",
      ".label { display: block; width: 100%; text-align: left; cursor: pointer;",
      "background: #fffaf3; border: 1px solid #1c1917; border-radius: 2px;",
      "padding: 6px 8px; font: inherit; font-size: 14px; line-height: 1.35; color: inherit; }",
      ".label:disabled { cursor: default; }",
      ".card { margin-top: 4px; background: #fffaf3; border: 1px solid #1c1917;",
      "padding: 8px; font-size: 14px; line-height: 1.4; }",
      ".card p { margin: 0 0 8px; }",
      ".close { font: inherit; font-size: 13px; background: transparent;",
      "border: 0; padding: 0; text-decoration: underline; cursor: pointer; color: inherit; }",
      ".listing { width: 220px; background: #fffaf3; border: 1px solid #1c1917; }",
      ".listing-link { display: grid; grid-template-columns: 72px 1fr; column-gap: 8px;",
      "row-gap: 2px; padding: 8px 8px 4px; color: inherit; text-decoration: none; }",
      ".listing img { width: 72px; height: 72px; object-fit: cover; grid-row: span 2; background: #efeae2; }",
      ".listing-name { font-size: 15px; line-height: 1.3; }",
      ".listing-price { font-size: 14px; }",
      ".listing-reason { margin: 0; padding: 0 8px 8px; font-size: 13px; line-height: 1.35; }",
    ].join("\n");
    return element;
  }

  function chatDock() {
    const dock = document.createElement("section");
    dock.className = "dock";
    dock.innerHTML =
      '<div class="thread" hidden></div>' +
      '<form class="ask">' +
      '<label class="caption" for="unmasked-question">Same agent as your calls and messages</label>' +
      '<div class="row">' +
      '<input id="unmasked-question" name="question" type="text" autocomplete="off" placeholder="Ask about this product">' +
      '<button type="submit">Send</button>' +
      "</div></form>";
    const thread = dock.querySelector(".thread");
    const form = dock.querySelector("form");
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const input = form.elements.question;
      const question = input.value.trim();
      if (!question) return;
      thread.hidden = false;
      appendMessage(thread, "you", question);
      appendMessage(thread, "agent", answer(question));
      input.value = "";
      thread.scrollTop = thread.scrollHeight;
    });
    return dock;
  }

  function appendMessage(thread, role, text) {
    const line = document.createElement("p");
    line.className = "bubble " + role;
    line.textContent = text;
    thread.appendChild(line);
  }

  function answer(question) {
    const text = question.toLowerCase();
    const product = productName();
    const price = currentNotes.find((note) => note.kind === "price");
    const listing = currentNotes.find((note) => note.kind === "recommendation");
    const concerns = currentNotes.filter((note) => note.kind === "concern" || note.kind === "product_info");
    if (price && /price|cost|tax|how much/.test(text)) return price.message;
    const concern = concerns.find((note) => topic(note, text));
    if (concern) return concern.message;
    if (listing && /better|instead|alternative|recommend|value|other product/.test(text)) {
      const amount = listing.price ? " for $" + Number(listing.price).toFixed(2) : "";
      const link = listing.productUrl || listing.product_url || "";
      return (listing.title || listing.productName) + amount + ". " + (listing.message || "") + (link ? " " + link : "");
    }
    const sentence = sentenceAbout(text);
    if (sentence) return sentence;
    return (
      "I saved that on the same thread as your calls and messages. " +
      "I don't have that detail for " +
      product +
      " yet."
    );
  }

  function topic(note, text) {
    const haystack = (note.title + " " + note.message).toLowerCase();
    if (/return|refund/.test(text)) return /return|refund/.test(haystack);
    if (/damage|warranty|guarantee/.test(text)) return /damage|warrant|guarantee/.test(haystack);
    if (/stock|available|ship/.test(text)) return /stock|ship|available/.test(haystack);
    return false;
  }

  function sentenceAbout(text) {
    const skip = new Set(["what", "when", "where", "this", "that", "with", "from", "have", "does", "about", "your", "product"]);
    const words = text.split(/\W+/).filter((word) => word.length > 3 && !skip.has(word));
    if (!words.length || !document.body) return "";
    const sentences = document.body.innerText.split(/(?<=[.!?])\s+/);
    return sentences.find((sentence) => words.some((word) => sentence.toLowerCase().includes(word))) || "";
  }

  function productName() {
    const title = document.querySelector("h1");
    return (title && title.innerText.trim()) || document.title || "this product";
  }

  function chatStyle() {
    const element = document.createElement("style");
    element.textContent = [
      ".dock { position: fixed; left: 50%; bottom: 16px; transform: translateX(-50%);",
      "width: min(560px, calc(100vw - 24px)); pointer-events: auto;",
      "background: #fffaf3; border: 1px solid #1c1917; color: #1c1917;",
      "font-family: Palatino, Georgia, serif; box-shadow: 0 8px 24px rgba(28, 25, 23, 0.12); }",
      ".thread { max-height: 240px; overflow: auto; display: flex; flex-direction: column; gap: 8px;",
      "padding: 12px 12px 0; }",
      ".bubble { margin: 0; max-width: 85%; font-size: 14px; line-height: 1.4; padding: 8px 10px; }",
      ".you { align-self: flex-end; background: #1c1917; color: #fffaf3; }",
      ".agent { align-self: flex-start; background: #f4efe6; }",
      ".ask { margin: 0; padding: 8px 12px 10px; }",
      ".caption { display: block; font-size: 12px; letter-spacing: 0.02em; margin-bottom: 6px; }",
      ".row { display: flex; gap: 8px; }",
      ".ask input { flex: 1; min-width: 0; font: inherit; font-size: 15px; color: inherit;",
      "background: transparent; border: 0; padding: 6px 0; }",
      ".ask button { font: inherit; font-size: 14px; background: #1c1917; color: #fffaf3;",
      "border: 0; padding: 8px 12px; cursor: pointer; }",
    ].join("\n");
    return element;
  }

  window.UnmaskedOverlay = { show, clear, mountChat };
})();
