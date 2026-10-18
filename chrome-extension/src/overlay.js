/* Product chat controller. The Allbirds-style panel lives in chat-ui.js. */
(function () {
  const CHAT_ID = "unmasked-chat";
  const POSITIVE = ["recycled", "organic", "sustainable", "renewable", "biodegradable", "repairable", "fair trade", "wool", "linen", "hemp", "cotton"];
  const NEGATIVE = ["polyester", "nylon", "acrylic", "plastic", "vinyl", "polyurethane", "non-recyclable"];
  const SUGGESTIONS = ["What's the return policy?", "What are the materials?", "Is there a greener option?"];

  let view = null;
  let currentSummary = null;
  let currentDossier = null;
  let currentVisits = [];
  let selectedId = "";
  const state = {
    open: false,
    expanded: false,
    menu: false,
    cartOpen: false,
    assistantName: "Your Online Assistant",
    phone: "",
    textStatus: "",
    summary: null,
    dossier: null,
    overview: [],
    pageProduct: null,
    outside: null,
    report: null,
    products: [],
    cart: [],
    messages: [],
    activity: "",
    sources: [],
    inboxMode: false,
    call: null,
    evidenceOpen: {},
    suggestions: SUGGESTIONS.slice(),
    account: null,
    authMode: "login",
    authError: "",
    reading: false,
    seeking: false,
    readingStep: 0,
    registry: null,
    readingSteps: [
      "Reading the product on this page",
      "Checking other sites for reviews and policies",
      "Checking the public registry",
      "Matching the same kind of product",
    ],
  };
  let readingTimer = null;
  let revealTimer = null;
  let pending = { notes: false, products: false };

  function threadKey() {
    return "unmaskedThread:" + location.href;
  }

  function loadThread() {
    try {
      const saved = JSON.parse(localStorage.getItem(threadKey()) || "[]");
      state.messages = Array.isArray(saved) ? saved.slice(-40) : [];
    } catch (error) {
      state.messages = [];
    }
  }

  function saveThread() {
    try {
      localStorage.setItem(threadKey(), JSON.stringify(state.messages.slice(-40)));
    } catch (error) {
      /* A store page can block storage. The thread still lives for this visit. */
    }
  }

  function render() {
    if (!view) return;
    view.render(state, actions);
  }

  function beginReading() {
    if (revealTimer) clearTimeout(revealTimer);
    pending = { notes: true, products: true };
    state.reading = true;
    state.readingStep = 0;
    state.summary = null;
    state.overview = [];
    state.outside = null;
    state.report = null;
    state.footprint = null;
    state.taste = null;
    state.registry = null;
    state.products = [];
    state.pageProduct = null;
    state.messages = [];
    currentSummary = null;
    currentDossier = null;
    state.open = true;
    if (readingTimer) clearInterval(readingTimer);
    readingTimer = setInterval(() => {
      state.readingStep = (state.readingStep + 1) % state.readingSteps.length;
      render();
    }, 1400);
    mountChat();
    render();
  }

  function reveal() {
    pending.notes = false;
    finishReading();
  }

  function finishReading() {
    if (pending.notes || pending.products) return;
    state.reading = false;
    state.seeking = false;
    if (readingTimer) clearInterval(readingTimer);
    readingTimer = null;
    loadThread();
    render();
  }

  function mountChat() {
    if (document.getElementById(CHAT_ID) || !document.body || !window.UnmaskedChat) return;
    const element = document.createElement("div");
    element.id = CHAT_ID;
    element.style.cssText = "position:fixed;inset:0;z-index:2147483647;pointer-events:none";
    const shadow = element.attachShadow({ mode: "open" });
    document.documentElement.appendChild(element);
    view = window.UnmaskedChat.mount(shadow);
    loadThread();
    render();
  }

  const actions = {
    open() {
      state.open = true;
      render();
    },
    close() {
      state.open = false;
      state.menu = false;
      render();
    },
    toggleExpand() {
      state.expanded = !state.expanded;
      render();
    },
    toggleMenu() {
      state.menu = !state.menu;
      state.cartOpen = false;
      render();
    },
    toggleCart() {
      state.cartOpen = !state.cartOpen;
      state.menu = false;
      render();
    },
    toggleEvidence(id) {
      state.evidenceOpen = Object.assign({}, state.evidenceOpen, { [id]: !state.evidenceOpen[id] });
      render();
    },
    send(text) {
      sendQuestion(text);
    },
    toggleAuthMode() {
      state.authMode = state.authMode === "register" ? "login" : "register";
      state.authError = "";
      render();
    },
    signIn(form) {
      const sign = window.UnmaskedOverlay && window.UnmaskedOverlay.signIn;
      state.authError = "";
      state.activity = "Signing in…";
      render();
      if (typeof sign !== "function") {
        state.activity = "";
        state.authError = "Sign-in is available from the extension.";
        render();
        return;
      }
      Promise.resolve(sign(form))
        .then((result) => {
          state.activity = "";
          if (!result || !result.token) {
            state.authError = (result && (result.detail || result.reason)) || "That email or password is not right.";
            render();
            return;
          }
          state.account = result.account;
          state.authError = "";
          render();
          if (typeof window.UnmaskedOverlay.onSignedIn === "function") window.UnmaskedOverlay.onSignedIn(result);
        })
        .catch(() => {
          state.activity = "";
          state.authError = "Sign-in could not reach the account service.";
          render();
        });
    },
    wishlist(product) {
      saveWishlist(product);
    },
    addToCart(product) {
      if (state.cart.some((item) => item.url === product.url)) return;
      state.cart = state.cart.concat([product]);
      state.cartOpen = true;
      if (typeof window.UnmaskedOverlay.onCartChange === "function") window.UnmaskedOverlay.onCartChange(state.cart);
      render();
    },
    purchase() {
      purchaseCart();
    },
    setInbox(open) {
      state.inboxMode = open;
      state.menu = false;
      state.messages = [];
      render();
      if (!open) return;
      const load = window.UnmaskedOverlay && window.UnmaskedOverlay.loadInbox;
      if (typeof load !== "function") return;
      Promise.resolve(load()).then((payload) => {
        state.messages = (payload && payload.messages ? payload.messages : []).map((message, index) => ({
          id: "inbox-" + index,
          role: message.role === "user" ? "you" : "agent",
          text: message.body,
        }));
        render();
      });
    },
    startCall() {
      startCall();
    },
    hangUp() {
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      state.call = null;
      render();
    },
  };

  function showSummary(input) {
    const next = summarize(input || {});
    if (!currentSummary || currentSummary.title !== next.title) selectedId = "";
    currentSummary = next;
    state.summary = next;
    const price = String(input.listedPrice || "").replace(/^\$/, "");
    if (input.url || input.imageUrl) {
      state.pageProduct = {
        name: next.title,
        url: input.url || location.href,
        store: input.store || "This page",
        price: price,
        imageUrl: input.imageUrl || "",
        message: input.price && input.price.message ? input.price.message : "",
        environmentScore: next.environment,
      };
    }
    refreshOverview();
    mountChat();
    state.open = true;
    render();
  }

  function summarize(input) {
    const pageText = String(input.pageText || "");
    const title = String(input.title || productName());
    const notes = Array.isArray(input.notes) ? input.notes : [];
    const materials = scoreWords(pageText, POSITIVE, NEGATIVE);
    const packaging = scoreWords(pageText, ["recyclable packaging", "plastic-free", "compostable", "paper mailer"], ["polybag", "plastic packaging", "plastic wrap"]);
    const claims = scoreWords(pageText, ["sustainable", "eco-friendly", "carbon neutral", "climate neutral", "low impact"], ["greenwash"]);
    const environment = Math.round((materials + packaging + claims) / 3);
    const bars = [
      { id: "environment", label: "Environment", value: environment, detail: environmentDetail(environment, pageText), points: sentencesMatching(pageText, POSITIVE.concat(NEGATIVE, ["packaging", "mailer", "sustainable", "eco", "carbon"])) },
      { id: "materials", label: "Materials", value: materials, detail: partDetail("materials", materials, pageText), points: sentencesMatching(pageText, POSITIVE.concat(NEGATIVE)) },
      { id: "packaging", label: "Packaging", value: packaging, detail: partDetail("packaging", packaging, pageText), points: sentencesMatching(pageText, ["packaging", "mailer", "polybag", "wrap", "compostable", "recyclable"]) },
      { id: "claims", label: "Claims", value: claims, detail: partDetail("claims", claims, pageText), points: sentencesMatching(pageText, ["sustainable", "eco-friendly", "eco", "carbon", "climate", "low impact"]) },
    ];
    concernBars(pageText, notes).forEach((bar) => bars.push(bar));
    const reviews = (Array.isArray(input.reviews) ? input.reviews : []).map((quote) => String(quote || "").trim()).filter(Boolean).slice(0, 6);
    const reviewChart = weighReviews(reviews);
    if (reviews.length) {
      bars.push({ id: "reviews", label: "Reviews", value: reviewChart.concern == null ? 50 : reviewChart.concern, detail: reviewChart.verdict, points: reviews, chart: reviewChart });
    }
    if (input.price && input.price.message) {
      bars.push({ id: "tax", label: "Tax", value: 55, detail: input.price.message });
    }
    const risks = bars.filter((bar) => !["environment", "materials", "packaging", "claims"].includes(bar.id) && bar.value >= 40);
    const headline = risks.length
      ? risks.length + " concern" + (risks.length === 1 ? "" : "s") + " on " + title + ". Environmental friendliness is " + environment + " out of 100."
      : title + " states no return, warranty, or damage limit. Environmental friendliness is " + environment + " out of 100.";
    return { title, headline, environment, bars, reviewChart, footprint: carbonFootprint(pageText, environment) };
  }

  function weighReviews(quotes) {
    const positiveWords = /\b(love|loved|great|excellent|comfortable|recommend|perfect|soft|durable|worth|dry|happy|pleased|amazing|best|quality)\b/i;
    const negativeWords = /\b(snag\w*|broke\w*|broken|rip\w*|disappoint\w*|cheap|smell\w*|tight|holes?|worst|poor|uncomfortable|fell apart|stain\w*|defect\w*|waste|terrible|bad|issues?|problems?|fail\w*|narrow|scratch\w*|leak\w*|[1-3]\s+out of\s+5|[1-3]\s+stars?)\b/i;
    let positive = 0;
    let negative = 0;
    const rows = quotes.map((quote) => {
      const praise = positiveWords.test(quote);
      const complaint = negativeWords.test(quote);
      let tone = "neutral";
      if (complaint) {
        tone = "negative";
        negative += 1;
      } else if (praise) {
        tone = "positive";
        positive += 1;
      }
      return { text: quote, tone };
    });
    const weighted = negative * 2;
    const total = positive + weighted;
    const concern = total ? Math.round((weighted / total) * 100) : null;
    let verdict = "These reviews do not lean clearly positive or negative.";
    if (concern != null && weighted > positive) verdict = "Complaints count twice, and they outweigh the praise.";
    else if (concern != null && positive > weighted) verdict = "Praise still outweighs the complaints, even with complaints counted twice.";
    else if (concern != null) verdict = "Praise and complaints are even after complaints are counted twice.";
    return { positive, negative, concern, verdict, rows };
  }

  function carbonFootprint(pageText, environment) {
    const hay = pageText.toLowerCase();
    const harms = NEGATIVE.filter((word) => hay.includes(word));
    const benefits = POSITIVE.filter((word) => hay.includes(word));
    const stated = pageText.match(/(\d+(?:\.\d+)?)\s*(?:kg|kilograms?)\s*(?:of\s+)?co2e?/i);
    const carbon = stated ? stated[0].replace(/\s+/g, " ") : "";
    let text = harms.length
      ? "Higher-impact materials named on this page: " + harms.join(", ") + "."
      : "This page does not name a higher-impact material such as polyester, nylon, or plastic.";
    if (benefits.length) text += " Lower-impact materials named: " + benefits.slice(0, 4).join(", ") + ".";
    text += carbon
      ? " The page states a carbon footprint of " + carbon + "."
      : " This page does not publish a carbon footprint.";
    return { text, carbon, harms, benefits, score: environment };
  }

  function scoreWords(text, positive, negative) {
    const hay = text.toLowerCase();
    let score = 50;
    positive.forEach((word) => {
      if (hay.includes(word)) score += 12;
    });
    negative.forEach((word) => {
      if (hay.includes(word)) score -= 12;
    });
    return Math.max(8, Math.min(96, score));
  }

  function environmentDetail(score, pageText) {
    if (!POSITIVE.concat(NEGATIVE).some((word) => pageText.toLowerCase().includes(word))) {
      return "The page does not describe materials, packaging, or an environmental claim, so this stays near the middle.";
    }
    if (score >= 70) return "The page names lower-impact materials more often than plastic or synthetic ones.";
    if (score <= 35) return "The page leans on plastic or synthetic materials, or it doesn't back an environmental claim.";
    return "The page mixes lower-impact words with conventional materials.";
  }

  function partDetail(part, score, pageText) {
    const sentence = sentenceWith(pageText, part === "materials" ? POSITIVE.concat(NEGATIVE) : part === "packaging" ? ["packaging", "mailer", "polybag", "wrap"] : ["sustainable", "eco", "carbon", "climate"]);
    if (sentence) return sentence;
    return "No " + part + " sentence on this page. The bar stays at " + score + " until the page says more.";
  }

  function concernBars(pageText, notes) {
    const found = [];
    const seen = new Set();
    notes.forEach((note) => {
      const message = String(note.message || note.label || "").trim();
      const label = concernLabel(note.title, message);
      if (!label || !message || seen.has(label)) return;
      seen.add(label);
      found.push({ id: label.toLowerCase(), label, value: concernValue(message), detail: message, points: [message] });
    });
    pageText.split(/(?<=[.!?])\s+/).forEach((sentence) => {
      const clean = sentence.replace(/\s+/g, " ").trim();
      const label = concernLabel("", clean);
      if (!label || clean.length < 36 || clean.length > 280) return;
      if (!/\d+\s*-?\s*(?:days?|hours?)|buyer protection|free returns?|refund|not as described|damag|defect|warrant|guarantee|money back|dispute|first week|final sale|no returns?|restock|fee|unworn|exclud|not covered|you pay|original tags/i.test(clean)) return;
      const existing = found.find((bar) => bar.label === label);
      if (existing) {
        if (!existing.points.includes(clean)) existing.points.push(clean);
        return;
      }
      seen.add(label);
      found.push({ id: label.toLowerCase(), label, value: concernValue(clean), detail: clean, points: [clean] });
    });
    ["Returns", "Warranty", "Damage"].forEach((label) => {
      if (seen.has(label)) return;
      const detail = "The page does not state a " + label.toLowerCase() + " limit.";
      found.push({ id: label.toLowerCase(), label, value: 12, detail, points: [detail] });
    });
    return found;
  }

  function concernLabel(title, text) {
    const hay = (title + " " + text).toLowerCase();
    if (/return|refund|exchange|buyer protection/.test(hay)) return "Returns";
    if (/warrant|guarantee/.test(hay)) return "Warranty";
    if (/damage/.test(hay)) return "Damage";
    if (/restock/.test(hay)) return "Restock";
    if (/cancel/.test(hay)) return "Cancel";
    return "";
  }

  function concernValue(text) {
    const hay = text.toLowerCase();
    if (/final sale|no returns|not covered/.test(hay)) return 90;
    if (/fee|restock|you pay/.test(hay)) return 72;
    if (/first week|7 day|14 day/.test(hay)) return 64;
    if (/30 day|unworn|exclud/.test(hay)) return 48;
    return 36;
  }

  function sentencesMatching(text, words) {
    const found = [];
    String(text || "").split(/\n|(?<=[.!?])\s+/).forEach((sentence) => {
      const clean = sentence.replace(/\s+/g, " ").trim();
      const hay = clean.toLowerCase();
      if (clean.length < 12 || clean.length > 280 || found.length >= 3) return;
      if (words.some((word) => hay.includes(word))) found.push(clean);
    });
    return found;
  }

  function sentenceWith(text, words) {
    return text.split(/(?<=[.!?])\s+/).map((sentence) => sentence.replace(/\s+/g, " ").trim()).find((sentence) => {
      const hay = sentence.toLowerCase();
      return sentence.length > 24 && sentence.length < 280 && words.some((word) => hay.includes(word));
    }) || "";
  }

  function summaryNotes() {
    const notes = currentSummary ? currentSummary.bars.map((bar) => ({ title: bar.label, message: bar.detail })) : [];
    const dossier = currentDossier || {};
    if (dossier.seller && dossier.seller.detail) notes.push({ title: "Seller", message: dossier.seller.detail });
    (dossier.reviews || []).slice(0, 3).forEach((review) => {
      if (review.quote) notes.push({ title: "Review", message: review.quote });
    });
    (dossier.documents || []).slice(0, 3).forEach((document) => {
      if (document.excerpt || document.title) notes.push({ title: document.title || "Document", message: document.excerpt || document.url || "" });
    });
    return notes;
  }

  function evidenceFromContext() {
    const items = [];
    (currentSummary ? currentSummary.bars : []).forEach((bar) => {
      const text = (bar.points && bar.points[0]) || bar.detail;
      if (text) items.push({ title: bar.label, text });
    });
    (currentDossier && currentDossier.reviews ? currentDossier.reviews : []).slice(0, 2).forEach((review) => {
      if (review.quote) items.push({ title: "Review", text: review.quote, url: review.url || "" });
    });
    currentVisits.slice(0, 3).forEach((visit) => {
      items.push({ title: visit.site || "Source", text: visit.reason || visit.title || "", url: visit.url });
    });
    return items.slice(0, 6);
  }

  function pushMessage(role, text, evidence, report) {
    const message = { id: Date.now() + "-" + Math.random().toString(16).slice(2), role, text, evidence: evidence || [] };
    if (report) message.report = report;
    state.messages = state.messages.concat([message]);
    if (!state.inboxMode) saveThread();
    return message;
  }

  function sendQuestion(question) {
    const text = String(question || "").trim();
    if (!text) return;
    mountChat();
    state.open = true;
    state.menu = false;
    pushMessage("you", text);
    state.activity = state.inboxMode ? "Sending…" : "Looking at this product…";
    render();
    if (state.inboxMode) {
      const send = window.UnmaskedOverlay && window.UnmaskedOverlay.sendInbox;
      if (typeof send !== "function") {
        state.activity = "";
        pushMessage("agent", "Messages open after the assistant is connected.");
        render();
        return;
      }
      Promise.resolve(send(text, state.cart, summaryNotes()))
        .then((payload) => {
          state.activity = "";
          pushMessage("agent", (payload && payload.answer) || "I couldn't reach the assistant.");
          render();
        })
        .catch(() => {
          state.activity = "";
          pushMessage("agent", "I couldn't reach the assistant.");
          render();
        });
      return;
    }
    const ask = window.UnmaskedOverlay && window.UnmaskedOverlay.ask;
    const finish = (reply) => {
      const payload = reply && typeof reply === "object" ? reply : { answer: reply };
      state.activity = "";
      if (Array.isArray(payload.products) && payload.products.length) state.products = payload.products;
      if (Array.isArray(payload.registry)) state.registry = payload.registry;
      const accepted = window.UnmaskedChat && window.UnmaskedChat.acceptReport ? window.UnmaskedChat.acceptReport(payload.report) : null;
      if (accepted) {
        state.report = accepted;
        if (accepted.followUps.length) state.suggestions = accepted.followUps.slice();
      }
      pushMessage("agent", payload.answer || answer(text), evidenceFromContext(), accepted);
      render();
    };
    if (typeof ask !== "function") {
      finish(answer(text));
      return;
    }
    Promise.resolve(ask(text)).then(finish).catch(() => {
      state.activity = "";
      pushMessage("agent", "I couldn't reach the agent just now.");
      render();
    });
  }

  function answer(question) {
    const text = question.toLowerCase();
    if (/source|website|where did you|which site/.test(text) && currentVisits.length) {
      return currentVisits.slice(0, 6).map((visit) => visit.site + " (" + visit.reason + ")").join(", ");
    }
    const bar = (currentSummary ? currentSummary.bars : []).find((item) => text.includes(item.label.toLowerCase()) || (item.id === "environment" && /environment|eco|green|sustain/.test(text)));
    if (bar) return bar.detail;
    return currentSummary ? currentSummary.headline : "I don't have that detail for this product yet.";
  }

  function productName() {
    const title = document.querySelector("h1");
    return (title && title.innerText.trim()) || document.title || "this product";
  }

  function showSources(visits) {
    currentVisits = Array.isArray(visits) ? visits.filter((visit) => visit && visit.url) : [];
    state.sources = currentVisits;
    mountChat();
    state.open = true;
    render();
  }

  function refreshOverview() {
    const sections = [];
    const dossier = state.dossier || {};
    const seller = dossier.seller || {};
    if (seller.detail || seller.name) {
      sections.push({ title: "Seller", text: seller.detail || seller.name, points: [] });
    }
    const bars = state.summary && state.summary.bars ? state.summary.bars : [];
    ["Returns", "Warranty", "Damage", "Tax"].forEach((label) => {
      const bar = bars.find((item) => item.label === label);
      if (!bar || !helpful(bar.detail)) return;
      const points = (bar.points || []).filter((point) => helpful(point) && point !== bar.detail).slice(0, 2);
      sections.push({ title: bar.label, text: bar.detail, points });
    });
    const outside = state.outside || { reviews: [], policies: [], environment: [] };
    (outside.policies || []).slice(0, 3).forEach((policy) => {
      if (!policy.text) return;
      sections.push({ title: policy.title || "Outside policy", text: policy.text, points: policy.url ? [policy.url] : [] });
    });
    const outsideQuotes = (outside.reviews || []).map((review) => review.quote).filter(Boolean);
    const chart = weighReviews(outsideQuotes);
    if (chart.rows.length) {
      sections.push({
        title: "Reviews",
        text: chart.verdict,
        chart,
        points: (outside.reviews || []).map((review) => (review.source ? review.source + " · " + review.quote : review.quote)),
      });
    } else {
      sections.push({ title: "Reviews", text: "No outside review mentioned this product.", points: [] });
    }
    if (!state.report) {
      sections.push({ title: "Carbon footprint", text: outsideFootprint(outside.environment || []), points: (outside.environment || []).map((row) => (row.source ? row.source + " · " + row.text : row.text)).filter(Boolean) });
    }
    (dossier.documents || []).slice(0, 3).forEach((document) => {
      const text = document.excerpt || "";
      if (helpful(text)) sections.push({ title: document.title || "Document", text, points: [] });
    });
    const specs = (dossier.specs || []).map((spec) => (spec.label ? spec.label + ": " + spec.value : spec.value)).filter((spec) => helpful(spec));
    if (specs.length) sections.push({ title: "Specifications", text: specs[0], points: specs.slice(1, 4) });
    state.overview = sections;
  }

  function outsideFootprint(rows) {
    const text = rows.map((row) => row.text || "").join(" ");
    if (!text.trim()) return "No outside source published a carbon footprint or a materials finding for this product.";
    const harms = NEGATIVE.filter((word) => text.toLowerCase().includes(word));
    const stated = text.match(/(\d+(?:\.\d+)?)\s*(?:kg|kilograms?)\s*(?:of\s+)?co2e?/i);
    let summary = harms.length
      ? "Outside sources name higher-impact materials: " + harms.join(", ") + "."
      : "Outside sources discuss this product's materials.";
    summary += stated
      ? " A source states a carbon footprint of " + stated[0].replace(/\s+/g, " ") + "."
      : " No outside source states a carbon footprint number.";
    return summary;
  }

  function showAccount(account) {
    state.account = account && account.email ? account : null;
    state.authError = "";
    if (state.account) state.open = true;
    mountChat();
    render();
  }

  function showSignedOut() {
    state.account = null;
    state.reading = false;
    state.open = true;
    mountChat();
    render();
  }

  function showFootprint(footprint) {
    state.footprint = footprint || null;
    mountChat();
    render();
  }

  function showTaste(taste) {
    state.taste = taste || null;
    mountChat();
    render();
  }

  function showRegistry(entries) {
    state.registry = Array.isArray(entries) ? entries : [];
    mountChat();
    render();
  }

  function showReport(report) {
    const accepted = window.UnmaskedChat && window.UnmaskedChat.acceptReport ? window.UnmaskedChat.acceptReport(report) : null;
    if (!accepted) return;
    state.report = accepted;
    if (accepted.followUps.length) state.suggestions = accepted.followUps.slice();
    refreshOverview();
    mountChat();
    state.open = true;
    render();
  }

  function showOutside(payload) {
    state.outside = payload || { reviews: [], policies: [], environment: [] };
    refreshOverview();
    mountChat();
    render();
  }

  function saveWishlist(product) {
    const save = window.UnmaskedOverlay && window.UnmaskedOverlay.wishlist;
    mountChat();
    state.open = true;
    if (typeof save !== "function") {
      pushMessage("agent", "The wishlist is available after the assistant is connected.");
      render();
      return;
    }
    state.activity = "Saving to your wishlist…";
    render();
    Promise.resolve(save(product))
      .then((reply) => {
        const payload = reply && typeof reply === "object" ? reply : { answer: reply };
        state.activity = "";
        pushMessage("agent", payload.answer || "Saved to your wishlist.");
        render();
      })
      .catch(() => {
        state.activity = "";
        pushMessage("agent", "I couldn't save that to the wishlist.");
        render();
      });
  }

  function helpful(text) {
    const value = String(text || "").replace(/\s+/g, " ").trim();
    if (value.length < 20) return false;
    if (/^no .+ sentence on this page/i.test(value)) return false;
    if (/the bar stays at|until the page says more|does not describe materials|does not state a/i.test(value)) return false;
    const labels = value.match(/\b(material|warranty|shipping|packaging|review)\b/gi) || [];
    if (new Set(labels.map((word) => word.toLowerCase())).size >= 3) return false;
    return true;
  }

  function showDossier(dossier) {
    currentDossier = dossier || null;
    state.dossier = currentDossier;
    refreshOverview();
    mountChat();
    if (dossier) state.open = true;
    render();
  }

  function showTextStatus(message) {
    mountChat();
    state.textStatus = message || "";
    render();
  }

  function beginCompare() {
    state.seeking = true;
    mountChat();
    render();
  }

  function showCarousel(products, note) {
    pending.products = false;
    state.seeking = false;
    const seen = new Set();
    state.products = (Array.isArray(products) ? products : [])
      .filter((product) => product && product.name && /^https?:/i.test(String(product.url || "")))
      .filter((product) => {
        const url = String(product.url || "");
        if (!url || seen.has(url)) return false;
        seen.add(url);
        return true;
      })
      .slice(0, 8);
    state.compareNote = note || (state.products.length ? "These listings came back from other stores." : "No other-store listing was retrieved for this kind of product.");
    mountChat();
    state.open = true;
    finishReading();
  }

  function showCart(items) {
    state.cart = Array.isArray(items) ? items.slice() : [];
    mountChat();
    render();
  }

  function purchaseCart() {
    const purchase = window.UnmaskedOverlay && window.UnmaskedOverlay.purchase;
    if (typeof purchase !== "function" || !state.cart.length) return;
    const buying = state.cart.slice();
    state.activity = "Placing these orders…";
    state.open = true;
    render();
    Promise.resolve(purchase(buying))
      .then((reply) => {
        const payload = reply && typeof reply === "object" ? reply : { answer: reply };
        state.activity = "";
        state.cart = [];
        state.cartOpen = false;
        pushMessage("agent", payload.answer || "Those orders are saved.");
        if (typeof window.UnmaskedOverlay.onCartChange === "function") window.UnmaskedOverlay.onCartChange(state.cart);
        render();
      })
      .catch(() => {
        state.activity = "";
        pushMessage("agent", "I couldn't save those orders just now.");
        render();
      });
  }

  function startCall() {
    state.menu = false;
    state.call = { status: "Calling your assistant…", body: "" };
    state.open = true;
    render();
    const call = window.UnmaskedOverlay && window.UnmaskedOverlay.startCall;
    if (typeof call !== "function") {
      state.call = { status: "Call unavailable", body: "" };
      render();
      return;
    }
    Promise.resolve(call(state.cart, summaryNotes()))
      .then((payload) => {
        const summary = (payload && payload.summary) || "The assistant didn't pick up.";
        state.call = { status: "On a call", body: summary };
        render();
        if (window.speechSynthesis) {
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(new SpeechSynthesisUtterance(summary));
        }
      })
      .catch(() => {
        state.call = { status: "The assistant didn't pick up.", body: "" };
        render();
      });
  }

  function setAssistant(profile) {
    if (!profile) return;
    if (profile.name) state.assistantName = profile.name;
    state.phone = profile.phoneDisplay || "";
    mountChat();
    render();
  }

  window.UnmaskedOverlay = {
    mountChat,
    beginReading,
    reveal,
    showSummary,
    summaryText() {
      return currentSummary ? currentSummary.headline : "";
    },
    summaryNotes,
    showSources,
    showDossier,
    showOutside,
    showReport,
    showFootprint,
    showRegistry,
    showAccount,
    showSignedOut,
    showTaste,
    showTextStatus,
    beginCompare,
    showCarousel,
    announce(text) {
      mountChat();
      state.open = true;
      state.activity = "";
      if (text) pushMessage("agent", text, evidenceFromContext());
      render();
    },
    showCart,
    setAssistant,
  };
})();
