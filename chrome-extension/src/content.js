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

const CHROME_TEXT = /keyboard shortcut|product summary presents|skip to|sponsored|customers who bought|sign in to|\$\{/i;

function visibleText(node) {
  return String((node && (node.innerText || node.textContent || node.content)) || "")
    .replace(/\s+/g, " ")
    .trim();
}

function pageHeading() {
  const selectors = ["#productTitle", "h1#title", "#title span", "[itemprop='name']", "h1"];
  for (let index = 0; index < selectors.length; index += 1) {
    const nodes = document.querySelectorAll(selectors[index]);
    for (let item = 0; item < nodes.length; item += 1) {
      const node = nodes[item];
      if (node.closest && node.closest("#unmasked-chat")) continue;
      const text = visibleText(node);
      if (text.length > 8 && text.length < 180 && !CHROME_TEXT.test(text)) return text;
    }
  }
  return "";
}

function productNames() {
  return readProducts()
    .map((product) => String((product && product.name) || "").replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .slice(0, 8);
}

function mainProduct() {
  const heading = pageHeading().toLowerCase();
  const products = readProducts();
  if (!heading) return products[0] || {};
  const words = heading.split(/\W+/).filter((word) => word.length > 3);
  let best = products[0] || {};
  let bestScore = -1;
  products.forEach((product) => {
    const name = String((product && product.name) || "").toLowerCase();
    const score = words.filter((word) => name.includes(word)).length;
    if (score > bestScore) {
      best = product;
      bestScore = score;
    }
  });
  return best;
}

function productRecord() {
  const product = mainProduct();
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
    name: productTitle(),
    heading: pageHeading(),
    candidates: productNames(),
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

function productImage() {
  const og = document.querySelector('meta[property="og:image"], meta[name="twitter:image"]');
  const fromMeta = og && (og.content || og.getAttribute("content"));
  if (fromMeta && /^https?:/i.test(fromMeta)) return fromMeta;
  const fromSchema = schemaImage(mainProduct());
  if (fromSchema) return fromSchema;
  const img = document.querySelector(
    "#landingImage, #imgBlkFront, #main-image, #imgTagWrapperId img, img[data-old-hires], [itemprop='image']"
  );
  if (!img || (img.closest && img.closest("#unmasked-chat"))) return "";
  const src = img.getAttribute("data-old-hires") || img.getAttribute("data-src") || img.currentSrc || img.src || "";
  return /^https?:/i.test(src) ? src : "";
}

function schemaImage(product) {
  const image = product && product.image;
  const value = Array.isArray(image) ? image[0] : image;
  if (!value) return "";
  const url = typeof value === "string" ? value : value.url || value.contentUrl || "";
  return /^https?:/i.test(String(url)) ? String(url) : "";
}

function listedPrice() {
  const selectors = [
    "#corePriceDisplay_desktop_feature_div .a-offscreen",
    "#corePrice_feature_div .a-offscreen",
    "#apex_offerDisplay_desktop .a-offscreen",
    "[itemprop='price']",
    "meta[property='product:price:amount']",
    "meta[property='og:price:amount']",
  ];
  for (let index = 0; index < selectors.length; index += 1) {
    const node = document.querySelector(selectors[index]);
    if (!node || (node.closest && node.closest("#unmasked-chat"))) continue;
    const raw = node.getAttribute("content") || visibleText(node);
    const amount = dollarAmount(raw);
    if (amount) return amount;
  }
  const column = document.querySelector("#centerCol, #ppd, main");
  return dollarAmount(column ? visibleText(column).slice(0, 2500) : "");
}

function dollarAmount(text) {
  const match = String(text || "").match(/\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?/);
  if (!match) return "";
  const number = match[1].replace(/,/g, "");
  if (Number(number) < 1) return "";
  return match[2] ? number + "." + match[2] : number + ".00";
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
  const heading = pageHeading();
  const og = document.querySelector('meta[property="og:title"]');
  const candidates = [heading, og && og.content, ...productNames(), document.title];
  for (let index = 0; index < candidates.length; index += 1) {
    const text = String(candidates[index] || "").replace(/\s+/g, " ").trim();
    const stripped = text.replace(/^(?:amazon\.com|walmart|ebay|etsy)\s*:\s*/i, "").replace(/\s*[-|–]\s*(aliexpress|amazon\.com|walmart|ebay|etsy).*$/i, "").trim();
    if (stripped.length > 8 && !CHROME_TEXT.test(stripped) && !/^(aliexpress|amazon|walmart|ebay|etsy)$/i.test(stripped)) return stripped.slice(0, 140);
  }
  return document.title || "This product";
}

function publishSummary() {
  if (!window.UnmaskedOverlay) return;
  const title = productTitle();
  const reviews = reviewQuotes();
  window.UnmaskedOverlay.showSummary({
    title,
    url: location.href,
    store: location.hostname.replace(/^www\./, ""),
    listedPrice: listedPrice(),
    imageUrl: productImage(),
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
  if (Array.isArray(payload.visits) && payload.visits.length && window.UnmaskedOverlay.showSources) {
    latestVisits = payload.visits;
    window.UnmaskedOverlay.showSources(payload.visits);
  }
  publishSummary();
  if (payload.report && window.UnmaskedOverlay.showReport) window.UnmaskedOverlay.showReport(payload.report);
  if (payload.footprint && window.UnmaskedOverlay.showFootprint) window.UnmaskedOverlay.showFootprint(payload.footprint);
  if (Array.isArray(payload.registry) && window.UnmaskedOverlay.showRegistry) window.UnmaskedOverlay.showRegistry(payload.registry);
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
    if (text.length < 20 || text.length > 400 || CHROME_TEXT.test(text)) continue;
    if (/return|refund|warranty|guarantee|buyer protection|damag|review|star|seller|policy|not as described|leather|material/i.test(text)) add(text);
  }
  document.querySelectorAll("details, [hidden], [aria-hidden='true']").forEach((element) => {
    if (!element.closest("#unmasked-chat")) add(element.textContent);
  });
  const column = document.querySelector("#centerCol, #ppd, main");
  if (column) add((column.innerText || "").slice(0, 4000));
  if (document.body) add((document.body.innerText || "").slice(0, 4000));
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

function maybeCaptureCheckout() {
  const path = location.pathname.toLowerCase();
  const title = (document.title || "").toLowerCase();
  const confirmation = /thank|order-received|order-confirm|checkout\/success|purchase-confirm/.test(path + " " + title);
  if (!confirmation || /^thank you$/.test(title.trim())) return;
  const key = "unmaskedCheckout:" + location.href;
  try {
    if (sessionStorage.getItem(key)) return;
  } catch (error) {
    return;
  }
  const items = checkoutItems();
  if (!items.length) return;
  try {
    sessionStorage.setItem(key, "1");
  } catch (error) {
    return;
  }
  chrome.runtime.sendMessage({ type: "unmasked-checkout", items }, () => {});
}

function checkoutItems() {
  const items = [];
  document.querySelectorAll('script[type="application/ld+json"]').forEach((node) => {
    let data = null;
    try {
      data = JSON.parse(node.textContent || "");
    } catch (error) {
      data = null;
    }
    collectCheckout(data, items);
  });
  if (items.length) return items.slice(0, 8);
  document.querySelectorAll("tr, li, [class*='line-item'], [class*='order-item']").forEach((row) => {
    if (items.length >= 8 || row.closest("#unmasked-chat")) return;
    const text = (row.innerText || "").replace(/\s+/g, " ").trim();
    const price = text.match(/\$\s*(\d+(?:\.\d{2})?)/);
    if (!price || text.length < 3 || text.length > 180) return;
    const name = text.replace(/\$\s*\d+(?:\.\d{2})?/, "").replace(/\s+/g, " ").trim();
    if (name.length < 3 || /subtotal|shipping|tax|total|discount/i.test(name)) return;
    items.push({ name: name.slice(0, 140), price: price[1], url: location.href, store: location.hostname.replace(/^www\./, "") });
  });
  return items;
}

function collectCheckout(data, items) {
  if (!data || items.length >= 8) return;
  if (Array.isArray(data)) {
    data.forEach((entry) => collectCheckout(entry, items));
    return;
  }
  const type = String(data["@type"] || "");
  if (/Product|OrderItem|Offer/i.test(type)) {
    const name = String(data.name || (data.itemOffered && data.itemOffered.name) || "").trim();
    const price = String((data.offers && data.offers.price) || data.price || "").trim();
    if (name) {
      items.push({
        name: name.slice(0, 140),
        price: price,
        url: String(data.url || location.href),
        store: location.hostname.replace(/^www\./, ""),
        brand: data.brand && (data.brand.name || data.brand),
        color: data.color || "",
      });
    }
  }
  ["orderedItem", "acceptedOffer", "itemListElement", "itemOffered"].forEach((key) => {
    if (data[key]) collectCheckout(data[key], items);
  });
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
    maybeCaptureCheckout();
    leavePage();
    return;
  }
  chrome.runtime.sendMessage({ type: "unmasked-session" }, (session) => {
    if (!window.UnmaskedOverlay) return;
    if (chrome.runtime.lastError || !session || !session.token) {
      if (window.UnmaskedOverlay.showSignedOut) window.UnmaskedOverlay.showSignedOut();
      return;
    }
    if (window.UnmaskedOverlay.showAccount) window.UnmaskedOverlay.showAccount(session.account);
    startReading();
  });
}

function startReading() {
  if (!requested && window.UnmaskedOverlay && window.UnmaskedOverlay.beginReading) window.UnmaskedOverlay.beginReading();
  publishSummary();
  requestNotes();
  requestAlternatives();
  requestTax();
}

function requestAlternatives() {
  if (!isProductPage() || alternativesTried) return;
  alternativesTried = true;
  if (window.UnmaskedOverlay && window.UnmaskedOverlay.beginCompare) window.UnmaskedOverlay.beginCompare();
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
      if (chrome.runtime.lastError || !response) {
        showAlternatives([]);
        return;
      }
      if (response.taste && window.UnmaskedOverlay && window.UnmaskedOverlay.showTaste) {
        window.UnmaskedOverlay.showTaste(response.taste);
      }
      if (Array.isArray(response.registry) && window.UnmaskedOverlay && window.UnmaskedOverlay.showRegistry) {
        window.UnmaskedOverlay.showRegistry(response.registry);
      }
      showAlternatives(Array.isArray(response.products) ? response.products : [], response.coverage || "");
    }
  );
}

function showAlternatives(products, note) {
  products = (products || []).filter(
    (product) => product && product.name && /^https?:/i.test(String(product.url || ""))
  );
  if (!window.UnmaskedOverlay || !window.UnmaskedOverlay.showCarousel) return;
  window.UnmaskedOverlay.showCarousel(products, note || "");
  if (!products.length || announcedAlternatives || !window.UnmaskedOverlay.announce) return;
  announcedAlternatives = true;
  window.UnmaskedOverlay.announce("These are similar products, using brands and colors you have kept.");
}

sync();

if (window.UnmaskedOverlay) {
  window.UnmaskedOverlay.onCartChange = (items) => {
    chrome.storage.local.set({ unmaskedCart: items });
  };
  chrome.storage.local.get({ unmaskedCart: [] }, (data) => {
    if (window.UnmaskedOverlay.showCart) window.UnmaskedOverlay.showCart(data.unmaskedCart || []);
  });
  window.UnmaskedOverlay.signIn = (form) =>
    new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: "unmasked-auth", mode: form.mode, email: form.email, password: form.password, name: form.name, phone: form.phone }, (response) => {
        resolve(chrome.runtime.lastError ? { detail: "Sign-in could not reach the account service." } : response || {});
      });
    });
  window.UnmaskedOverlay.onSignedIn = (result) => {
    const update = result && result.update;
    if (update && update.text && window.UnmaskedOverlay.announce) {
      const note = update.sent ? update.text : update.text + " " + (update.reason || "");
      window.UnmaskedOverlay.announce(note);
    }
    requested = false;
    alternativesTried = false;
    startReading();
  };
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
