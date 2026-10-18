/* The assistant stays off until the page is one product. */
let latestNotes = [];
let latestVisits = [];
let latestDossier = null;
let latestOutside = null;
let priceNote = null;
let requested = false;
let introTried = false;
let alternativesTried = false;
let announcedAlternatives = false;
let lastHref = location.href;

function isProductPage() {
  if (location.protocol !== "http:" && location.protocol !== "https:") return false;
  const host = location.hostname.toLowerCase().replace(/^www\./, "");
  if (
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "google.com" ||
    host.endsWith(".google.com") ||
    ["youtube.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "wikipedia.org", "github.com"].some(
      (blocked) => host === blocked || host.endsWith("." + blocked)
    )
  ) {
    return false;
  }
  const path = location.pathname.toLowerCase();
  if (/\/(search|cart|checkout|account|login|blog|help|category|categories|collections|browse|gp\/browse)(\/|$)|(?:^|\/)s(\/|$)/.test(path)) {
    return false;
  }
  if (hasProductSchema() || hasProductType()) return true;
  const productPath = /\/(products|product|dp|gp\/product|ip|itm|listing|item|p)\/[^/?#]+/.test(path);
  return productPath && (Boolean(listedPrice()) || hasBuyButton());
}

function hasProductType() {
  const meta = document.querySelector('meta[property="og:type"]');
  if (meta && String(meta.content || "").toLowerCase() === "product") return true;
  return Boolean(document.querySelector('[itemtype*="schema.org/Product"], [itemtype*="schema.org/product"]'));
}

function hasProductSchema() {
  return readProducts().length > 0;
}

function hasBuyButton() {
  const controls = document.querySelectorAll("button, [role='button'], input[type='submit']");
  return Array.from(controls).some((control) => /add to (cart|bag)|buy now|buy it now/i.test(control.innerText || control.value || ""));
}

function readProducts() {
  const products = [];
  document.querySelectorAll('script[type="application/ld+json"]').forEach((script) => {
    try {
      collectProducts(JSON.parse(script.textContent || ""), products);
    } catch (error) {
      /* A store's structured data is not always valid JSON. */
    }
  });
  return products;
}

function collectProducts(node, products) {
  if (!node) return;
  if (Array.isArray(node)) {
    node.forEach((item) => collectProducts(item, products));
    return;
  }
  if (typeof node !== "object") return;
  if (node["@graph"]) collectProducts(node["@graph"], products);
  const types = [].concat(node["@type"] || []).map((type) => String(type).toLowerCase());
  if (types.some((type) => type.includes("product") && !type.includes("group"))) products.push(node);
}

function productRecord() {
  const product = readProducts()[0] || {};
  const offer = [].concat(product.offers || [])[0] || {};
  const brand = named(product.brand);
  const seller = named(offer.seller);
  const reviews = []
    .concat(product.review || [])
    .map((review) => ({
      quote: String((review && review.reviewBody) || "").trim(),
      source: String((review && review.author && (review.author.name || review.author)) || "This page"),
      url: "",
    }))
    .filter((review) => review.quote)
    .slice(0, 6);
  return {
    name: String(product.name || productTitle() || "").trim(),
    seller: String(seller || "").trim(),
    brand: String(brand || "").trim(),
    reviews: reviews.concat(reviewQuotes().map((quote) => ({ quote, source: "This page", url: "" }))).slice(0, 8),
    documents: documentLinks(),
    specs: specRows(),
    description: productDescription(),
  };
}

function reviewQuotes() {
  const quotes = [];
  const seen = new Set();
  const nodes = document.querySelectorAll("[class*='review' i], [class*='feedback' i], [id*='review' i], p, li");
  for (let index = 0; index < nodes.length && quotes.length < 8 && index < 1200; index += 1) {
    const element = nodes[index];
    if (element.closest("#unmasked-chat, [class*='recommend' i], [class*='similar' i], [class*='carousel' i], [class*='sponsored' i], [class*='related' i]")) continue;
    if (element.querySelector("p, li")) continue;
    const text = (element.innerText || "").replace(/\s+/g, " ").trim();
    if (text.length < 40 || text.length > 320 || seen.has(text)) continue;
    if (!/\bstars?\b|out of 5|verified|reviewer|customers say|buyer|arrived|quality|broke|seller/i.test(text)) continue;
    seen.add(text);
    quotes.push(text);
  }
  return quotes;
}

function named(value) {
  if (!value) return "";
  if (typeof value === "string") return value.trim();
  return String(value.name || "").trim();
}

function documentLinks() {
  const links = [];
  const seen = new Set();
  document.querySelectorAll("a[href]").forEach((link) => {
    const label = (link.innerText || "").trim();
    const href = link.href || "";
    if (!href || seen.has(href) || !/manual|spec|datasheet|warranty|guarantee|return|refund|policy|guide|seller/i.test(label + " " + href)) {
      return;
    }
    seen.add(href);
    links.push({ title: label || href, url: href, kind: "document" });
  });
  return links.slice(0, 8);
}

function specRows() {
  const rows = [];
  document.querySelectorAll("tr").forEach((row) => {
    const cells = row.querySelectorAll("th, td");
    if (cells.length < 2 || rows.length >= 8) return;
    const label = (cells[0].innerText || "").replace(/\s+/g, " ").trim();
    const value = (cells[1].innerText || "").replace(/\s+/g, " ").trim();
    if (!label || !value || label.length > 40 || value.length > 80) return;
    if (!/material|fabric|weight|dimension|size|color|colour|made in|capacity|battery|model/i.test(label)) return;
    rows.push({ label, value });
  });
  return rows;
}

function leavePage() {
  const existing = document.getElementById("unmasked-chat");
  if (existing) existing.remove();
  requested = false;
  latestNotes = [];
  latestVisits = [];
  latestDossier = null;
  priceNote = null;
}

function listedPrice() {
  const text = document.body ? document.body.innerText : "";
  const match = text.match(/\$\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?/);
  if (!match) return "";
  const number = match[1].replace(/,/g, "");
  return number.includes(".") ? number : number + ".00";
}

function shopperZip() {
  const text = document.body ? document.body.innerText : "";
  const labeled = text.match(
    /(?:deliver(?:y| to)?|ship(?:ping)? to|pickup(?: at)?|store in|near)\s+[^\n]{0,80}?(\d{5})(?:-\d{4})?/i
  );
  if (labeled) return labeled[1];
  const city = text.match(/\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)?,\s*(?:[A-Z]{2}\s+)?(\d{5})\b/);
  return city ? city[1] : "";
}

function productDescription() {
  const schema = String((readProducts()[0] || {}).description || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (schema.length > 40) return schema.slice(0, 800);
  const meta = document.querySelector('meta[name="description"]');
  const metaText = String((meta && meta.content) || "").replace(/\s+/g, " ").trim();
  const words = productTitle()
    .toLowerCase()
    .split(/\W+/)
    .filter((word) => word.length > 3);
  if (metaText && words.some((word) => metaText.toLowerCase().includes(word))) return metaText.slice(0, 800);
  return "";
}

function productTitle() {
  const schemaName = String((readProducts()[0] || {}).name || "").replace(/\s+/g, " ").trim();
  const heading = document.querySelector("h1");
  const og = document.querySelector('meta[property="og:title"]');
  const candidates = [schemaName, heading && heading.innerText, og && og.content, document.title];
  for (let index = 0; index < candidates.length; index += 1) {
    const text = String(candidates[index] || "").replace(/\s+/g, " ").trim();
    const stripped = text.replace(/\s*[-|–]\s*(aliexpress|amazon\.com|walmart|ebay|etsy).*$/i, "").trim();
    if (stripped.length > 8 && !/^(aliexpress|amazon|walmart|ebay|etsy)$/i.test(stripped)) return stripped.slice(0, 140);
  }
  return document.title || "This product";
}

function publishSummary() {
  if (!window.UnmaskedOverlay) return;
  const title = productTitle();
  const reviews = reviewQuotes();
  const image = document.querySelector('meta[property="og:image"]');
  window.UnmaskedOverlay.showSummary({
    title,
    url: location.href,
    store: location.hostname.replace(/^www\./, ""),
    listedPrice: listedPrice(),
    imageUrl: image && image.content ? image.content : "",
    pageText: pageContext(),
    notes: latestNotes,
    price: priceNote,
    reviews,
  });
  if (reviews.length && window.UnmaskedOverlay.showDossier) {
    const current = latestDossier || {};
    window.UnmaskedOverlay.showDossier({
      name: title,
      seller: current.seller || {},
      reviews: reviews.map((quote) => ({ quote, source: "This page", url: "" })),
      documents: current.documents || [],
      specs: current.specs || [],
    });
  }
  sendFirstText();
}

function sendFirstText() {
  if (introTried || !window.UnmaskedOverlay || !window.UnmaskedOverlay.summaryText) return;
  const text = window.UnmaskedOverlay.summaryText();
  if (!text) return;
  introTried = true;
  chrome.storage.local.get({ unmaskedIntroduced: false }, (data) => {
    if (data.unmaskedIntroduced) return;
    chrome.runtime.sendMessage({ type: "unmasked-intro", text }, (response) => {
      if (!chrome.runtime.lastError && response && response.sent) {
        chrome.storage.local.set({ unmaskedIntroduced: true });
      }
    });
  });
}

function applyResult(payload) {
  if (!payload || !window.UnmaskedOverlay) return;
  if (payload.active === false) {
    leavePage();
    return;
  }
  latestNotes = Array.isArray(payload.notes) ? payload.notes : [];
  if (payload.outside && window.UnmaskedOverlay.showOutside) {
    latestOutside = payload.outside;
    window.UnmaskedOverlay.showOutside(payload.outside);
  }
  if (payload.dossier && window.UnmaskedOverlay.showDossier) {
    latestDossier = payload.dossier;
    if (!Array.isArray(latestDossier.reviews) || !latestDossier.reviews.length) {
      latestDossier.reviews = reviewQuotes().map((quote) => ({ quote, source: "This page", url: "" }));
    }
    window.UnmaskedOverlay.showDossier(latestDossier);
  }
  priceNote = latestNotes.find((note) => note.kind === "price") || priceNote;
  const recommended = latestNotes
    .filter((note) => note.kind === "recommendation" && note.productUrl && note.price)
    .map((note) => ({
      name: note.productName || note.title,
      url: note.productUrl,
      store:
        [
          { environmental: "Greener", cost_value: "Better value", durability: "More durable", reviews: "Better reviewed" }[note.aspect],
          note.store,
        ]
          .filter(Boolean)
          .join(" · ") || "Review",
      price: note.price,
      imageUrl: note.imageUrl || "",
      message: note.message || "",
      quotation: note.quotation || "",
      environmentScore: note.environmentScore,
    }));
  showAlternatives(recommended);
  if (Array.isArray(payload.visits) && payload.visits.length && window.UnmaskedOverlay.showSources) {
    latestVisits = payload.visits;
    window.UnmaskedOverlay.showSources(payload.visits);
  }
  publishSummary();
  if (payload.report && window.UnmaskedOverlay.showReport) window.UnmaskedOverlay.showReport(payload.report);
  sendProductText(payload.brief || "");
}

function sendProductText(brief) {
  const text = String(brief || "").trim();
  if (!text) return;
  chrome.storage.local.get({ unmaskedTexted: {} }, (data) => {
    const sent = data.unmaskedTexted || {};
    if (sent[location.href]) return;
    chrome.runtime.sendMessage({ type: "unmasked-intro", text }, (response) => {
      if (chrome.runtime.lastError || !response) return;
      if (response.sent) {
        sent[location.href] = true;
        chrome.storage.local.set({ unmaskedTexted: sent });
        if (window.UnmaskedOverlay.showTextStatus) window.UnmaskedOverlay.showTextStatus("Text sent.");
        return;
      }
      if (window.UnmaskedOverlay.showTextStatus) {
        window.UnmaskedOverlay.showTextStatus(response.reason || "The Photon text was not delivered.");
      }
    });
  });
}

function pageContext() {
  const chunks = [];
  const seen = new Set();
  function add(text) {
    const clean = String(text || "").replace(/\s+/g, " ").trim();
    if (clean.length < 20 || seen.has(clean) || chunks.join("\n").length > 12000) return;
    seen.add(clean);
    chunks.push(clean);
  }
  const nodes = document.querySelectorAll(
    "[class*='review' i], [class*='feedback' i], [class*='protect' i], [class*='return' i], [class*='refund' i], [class*='warrant' i], [class*='policy' i], p, li, span"
  );
  for (let index = 0; index < nodes.length && index < 1500; index += 1) {
    const element = nodes[index];
    if (element.closest("#unmasked-chat") || element.querySelector("p, li, section")) continue;
    const text = (element.innerText || element.textContent || "").trim();
    if (text.length < 20 || text.length > 400) continue;
    if (/return|refund|warranty|guarantee|buyer protection|damag|review|star|seller|policy|not as described/i.test(text)) add(text);
  }
  document.querySelectorAll("details, [hidden], [aria-hidden='true']").forEach((element) => {
    if (!element.closest("#unmasked-chat")) add(element.textContent);
  });
  if (document.body) add((document.body.innerText || "").slice(0, 6000));
  return chunks.join("\n").slice(0, 12000);
}

function requestTax() {
  const amount = listedPrice();
  const postal = shopperZip();
  if (!amount || !postal || priceNote) return;
  chrome.runtime.sendMessage({ type: "unmasked-tax", amount, postalCode: postal }, (response) => {
    if (chrome.runtime.lastError || !response || !response.note) return;
    priceNote = response.note;
    publishSummary();
  });
}

function requestNotes() {
  if (!isProductPage() || requested) return;
  requested = true;
  chrome.runtime.sendMessage(
    {
      type: "unmasked-analyze",
      url: location.href,
      listedPrice: listedPrice(),
      postalCode: shopperZip(),
      pageText: pageContext(),
      record: productRecord(),
      productPage: true,
    },
      (response) => {
      if (chrome.runtime.lastError) {
        publishSummary();
        if (window.UnmaskedOverlay && window.UnmaskedOverlay.reveal) window.UnmaskedOverlay.reveal();
        return;
      }
      applyResult(response);
      if (window.UnmaskedOverlay && window.UnmaskedOverlay.reveal) window.UnmaskedOverlay.reveal();
    }
  );
}

function sync() {
  if (location.href !== lastHref) {
    lastHref = location.href;
    requested = false;
    introTried = false;
    alternativesTried = false;
    announcedAlternatives = false;
  }
  if (!isProductPage()) {
    leavePage();
    return;
  }
  if (!requested && window.UnmaskedOverlay && window.UnmaskedOverlay.beginReading) window.UnmaskedOverlay.beginReading();
  requestNotes();
  requestAlternatives();
  requestTax();
}

function requestAlternatives() {
  if (!isProductPage() || alternativesTried) return;
  alternativesTried = true;
  const record = productRecord();
  chrome.runtime.sendMessage(
    {
      type: "unmasked-alternatives",
      name: record.name || productTitle(),
      url: location.href,
      pageText: String(record.description || "").slice(0, 800),
      listedPrice: listedPrice(),
    },
    (response) => {
      if (chrome.runtime.lastError || !response || !Array.isArray(response.products) || !response.products.length) return;
      showAlternatives(response.products);
    }
  );
}

function showAlternatives(products) {
  products = (products || []).filter((product) => product && /^https?:/i.test(String(product.imageUrl || "")));
  if (!products.length || !window.UnmaskedOverlay || !window.UnmaskedOverlay.showCarousel) return;
  window.UnmaskedOverlay.showCarousel(products);
  if (announcedAlternatives || !window.UnmaskedOverlay.announce) return;
  announcedAlternatives = true;
  window.UnmaskedOverlay.announce("These alternatives score better on materials, reviews, or price.");
}

sync();

if (window.UnmaskedOverlay) {
  window.UnmaskedOverlay.onCartChange = (items) => {
    chrome.storage.local.set({ unmaskedCart: items });
  };
  chrome.storage.local.get({ unmaskedCart: [] }, (data) => {
    if (window.UnmaskedOverlay.showCart) window.UnmaskedOverlay.showCart(data.unmaskedCart || []);
  });
  window.UnmaskedOverlay.wishlist = (product) =>
    new Promise((resolve) => {
      chrome.runtime.sendMessage(
        {
          type: "unmasked-wishlist",
          name: product.name,
          url: product.url,
          store: product.store,
          price: product.price,
          imageUrl: product.imageUrl,
          environmentScore: product.environmentScore,
        },
        (response) => {
          if (chrome.runtime.lastError || !response) {
            resolve({ answer: "I couldn't save that to the wishlist." });
            return;
          }
          resolve(response);
        }
      );
    });
  window.UnmaskedOverlay.purchase = (items) =>
    new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: "unmasked-checkout", items }, (response) => {
        if (chrome.runtime.lastError || !response) {
          resolve({ answer: "I couldn't save those orders just now." });
          return;
        }
        resolve(response);
      });
    });
  chrome.runtime.sendMessage({ type: "unmasked-assistant" }, (response) => {
    if (!chrome.runtime.lastError && response && window.UnmaskedOverlay.setAssistant) {
      window.UnmaskedOverlay.setAssistant(response);
    }
  });
  window.UnmaskedOverlay.loadInbox = () =>
    new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: "unmasked-inbox" }, (response) => {
        resolve(chrome.runtime.lastError ? { messages: [] } : response || { messages: [] });
      });
    });
  window.UnmaskedOverlay.sendInbox = (text, items, notes) =>
    new Promise((resolve) => {
      chrome.runtime.sendMessage(
        {
          type: "unmasked-inbox-send",
          text,
          cart: items || [],
          notes: notes || (window.UnmaskedOverlay.summaryNotes ? window.UnmaskedOverlay.summaryNotes() : []),
        },
        (response) => {
          resolve(chrome.runtime.lastError ? { answer: "I couldn't reach the assistant." } : response);
        }
      );
    });
  window.UnmaskedOverlay.startCall = (items, notes) =>
    new Promise((resolve) => {
      chrome.runtime.sendMessage(
        {
          type: "unmasked-call",
          cart: items || [],
          notes: notes || (window.UnmaskedOverlay.summaryNotes ? window.UnmaskedOverlay.summaryNotes() : []),
        },
        (response) => {
        resolve(chrome.runtime.lastError ? { summary: "The assistant didn't pick up." } : response);
      });
    });
  window.UnmaskedOverlay.ask = (question) =>
    new Promise((resolve) => {
      chrome.runtime.sendMessage(
        {
          type: "unmasked-ask",
          question,
          url: location.href,
          title: document.title,
          pageText: document.body ? document.body.innerText.slice(0, 6000) : "",
          notes: window.UnmaskedOverlay.summaryNotes ? window.UnmaskedOverlay.summaryNotes() : [],
          visits: latestVisits,
          dossier: latestDossier || {},
          outside: latestOutside || {},
          productPage: true,
        },
        (response) => {
          if (chrome.runtime.lastError || !response) {
            resolve("I couldn't reach the agent just now.");
            return;
          }
          resolve(response);
        }
      );
    });
}

let watchTimer = 0;
const watcher = new MutationObserver(() => {
  if (watchTimer) return;
  watchTimer = setTimeout(() => {
    watchTimer = 0;
    sync();
  }, 500);
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
