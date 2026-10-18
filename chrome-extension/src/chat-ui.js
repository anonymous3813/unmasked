/* React chat shell styled after the Allbirds shopping agent. */
(function () {
  const h = React.createElement;

  function ChatView({ state, actions }) {
    const threadRef = React.useRef(null);
    React.useEffect(() => {
      const node = threadRef.current;
      if (node) node.scrollTop = node.scrollHeight;
    }, [state.messages, state.activity, state.open]);

    return h(
      "div",
      { className: "dock" + (state.open ? " open" : "") },
      state.open
        ? h(Panel, { state, actions, threadRef })
        : h(
            "button",
            { type: "button", className: "launcher", onClick: actions.open },
            h(Mark, null),
            h(
              "span",
              { className: "launcher-copy" },
              h("strong", null, "Shop with AI"),
              h("span", null, "Shopping Agent")
            )
          )
    );
  }

  function Panel({ state, actions, threadRef }) {
    const [view, setView] = React.useState("discover");
    const seenMessages = React.useRef(0);
    React.useEffect(() => {
      if (seenMessages.current && state.messages.length > seenMessages.current) setView("ask");
      seenMessages.current = state.messages.length;
    }, [state.messages.length]);
    let body = h(Discover, { state: state, actions: actions });
    if (!state.account) body = h(AccountGate, { state: state, actions: actions });
    else if (view === "compare") body = h(Compare, { state: state, actions: actions });
    else if (view === "ask") body = h(Ask, { state: state, actions: actions });
    return h(
      "section",
      { className: "panel side" + (state.expanded ? " expanded" : "") + (state.reading ? " reading" : ""), "aria-label": "Unmasked shopping agent" },
      h(Header, { state: state, actions: actions }),
      state.reading || !state.account ? null : h(ViewNav, { view: view, onChoose: setView }),
      h("div", { className: "stage", ref: threadRef }, state.reading ? h(Reading, { state: state }) : body),
      state.cartOpen ? h(CartSheet, { state: state, actions: actions }) : null,
      state.menu ? h(MenuSheet, { state: state, actions: actions }) : null,
      state.call ? h(CallSheet, { call: state.call, onHangUp: actions.hangUp }) : null,
      state.reading || !state.account || view !== "ask" ? null : h(Composer, { placeholder: state.inboxMode ? "Message your assistant" : "Ask about this product", onSend: actions.send })
    );
  }

  function AccountGate({ state, actions }) {
    return h(
      "form",
      {
        className: "login",
        onSubmit: (event) => {
          event.preventDefault();
          const data = new FormData(event.target);
          actions.signIn({
            mode: state.authMode || "login",
            email: data.get("email"),
            password: data.get("password"),
            name: data.get("name") || "",
            phone: data.get("phone") || "",
          });
        },
      },
      h("h2", null, state.authMode === "register" ? "Create your account" : "Sign in"),
      h("p", { className: "hero" }, "Orders, the wishlist, and similar products stay with this account. The public registry does not."),
      state.authMode === "register" ? h("input", { name: "name", placeholder: "Name", autoComplete: "name", required: true }) : null,
      h("input", { name: "email", type: "email", placeholder: "Email", autoComplete: "email", required: true }),
      h("input", { name: "password", type: "password", placeholder: "Password", autoComplete: state.authMode === "register" ? "new-password" : "current-password", required: true, minLength: 8 }),
      h("input", { name: "phone", type: "tel", placeholder: "Mobile number for texts", autoComplete: "tel", required: true }),
      state.authError ? h("p", { className: "activity" }, state.authError) : null,
      h("button", { type: "submit" }, state.authMode === "register" ? "Create account" : "Log in"),
      h(
        "button",
        { type: "button", onClick: actions.toggleAuthMode },
        state.authMode === "register" ? "I already have an account" : "Create an account"
      )
    );
  }

  function ViewNav({ view, onChoose }) {
    const tabs = [
      ["discover", "Discover"],
      ["compare", "Compare"],
      ["ask", "Ask AI"],
    ];
    return h(
      "nav",
      { className: "views", "aria-label": "Shopping views" },
      tabs.map((tab) =>
        h(
          "button",
          {
            key: tab[0],
            type: "button",
            "aria-pressed": view === tab[0] ? "true" : "false",
            onClick: () => onChoose(tab[0]),
          },
          tab[1]
        )
      )
    );
  }

  function Discover({ state, actions }) {
    const product = state.pageProduct && state.pageProduct.name ? state.pageProduct : null;
    const policies = h(PolicyConcerns, { state: state });
    const footprint = h(Footprint, { footprint: state.footprint });
    const registry = h(RegistryNotes, { entries: state.registry });
    const reviews = h(ReviewPage, { state: state });
    return h(
      "div",
      { className: "page" },
      h(Welcome, { state: state }),
      product ? h(ProductRail, { products: [product], onAdd: actions.addToCart, stacked: true }) : null,
      policies,
      footprint,
      registry,
      reviews
    );
  }

  function Compare({ state, actions }) {
    const products = (state.products || []).filter((product) => product && product.name && /^https?:/i.test(String(product.url || "")));
    const taste = state.taste || {};
    const kept = [].concat(taste.brands || [], taste.colors || []).filter(Boolean);
    const note = state.compareNote || (products.length
      ? "These are the same kind of product as the one on this page."
      : "No other-store listing was retrieved for this kind of product.");
    return h(
      "div",
      { className: "page" },
      h(
        "article",
        { className: "section-page visual" },
        h("h2", null, "Is there a better product?"),
        kept.length ? h("p", { className: "hero" }, "Based on what you kept: " + kept.join(", ") + ".") : null,
        h("p", { className: "hero" }, note),
        products.length ? h(ProductRail, { products: products, onAdd: actions.addToCart, onWishlist: actions.wishlist, stacked: true }) : null
      )
    );
  }

  function Ask({ state, actions }) {
    return h(
      "div",
      { className: "page" },
      state.messages.map((message) =>
        h(Message, {
          key: message.id,
          message: message,
          open: Boolean(state.evidenceOpen[message.id]),
          onToggle: () => actions.toggleEvidence(message.id),
          report: message.report,
          state: state,
          actions: actions,
        })
      ),
      state.activity ? h("p", { className: "activity", role: "status" }, state.activity) : null,
      h(Suggestions, { suggestions: state.suggestions, onPick: actions.send }),
      state.report && state.report.suggestedActions && state.report.suggestedActions.length
        ? h(ActionList, { actions: state.report.suggestedActions, state: state, run: actions })
        : null
    );
  }

  const BLOCK_TYPES = {
    summary_card: true,
    sustainability_report: true,
    missing_evidence: true,
    source_list: true,
    suggested_action: true,
    follow_up: true,
  };
  const ACTION_TYPES = {
    compare_alternatives: true,
    save_product: true,
    open_source: true,
    open_product: true,
    ask_follow_up: true,
  };

  function acceptReport(report) {
    if (!report || report.demo !== false || !Array.isArray(report.blocks)) return null;
    const sources = (Array.isArray(report.sources) ? report.sources : []).filter(
      (source) => source && source.id && /^https?:/i.test(String(source.url || ""))
    );
    const blocks = report.blocks.filter((block) => block && BLOCK_TYPES[block.type]);
    const suggestedActions = (Array.isArray(report.suggestedActions) ? report.suggestedActions : []).filter(
      (action) => action && ACTION_TYPES[action.type]
    );
    return {
      responseId: String(report.responseId || ""),
      summary: String(report.summary || ""),
      demo: false,
      blocks: blocks,
      sources: sources,
      suggestedActions: suggestedActions,
      followUps: (Array.isArray(report.followUps) ? report.followUps : []).filter((item) => typeof item === "string").slice(0, 3),
    };
  }

  function collectPages(state, actions) {
    return [
      {
        id: "product",
        title: "This product",
        body: h(
          "div",
          { className: "page" },
          h(Welcome, { state: state }),
          state.pageProduct ? h(ProductRail, { products: [state.pageProduct], onAdd: actions.addToCart, stacked: true }) : null
        ),
      },
      {
        id: "policies",
        title: "Policy concerns",
        body: h("div", { className: "page" }, h(PolicyConcerns, { state: state })),
      },
      {
        id: "products",
        title: "Similar products",
        body: h(
          "div",
          { className: "page" },
          h(
            "article",
            { className: "section-page visual" },
            h("h2", null, "Similar products"),
            (state.products || []).filter(pictured).length
              ? h(ProductRail, { products: (state.products || []).filter(pictured), onAdd: actions.addToCart, onWishlist: actions.wishlist, stacked: true })
              : null
          )
        ),
      },
      {
        id: "carbon",
        title: "Carbon footprint",
        body: h("div", { className: "page" }, h(Footprint, { figure: carbonFigure(state.report) })),
      },
      {
        id: "reviews",
        title: "Reviews",
        body: h("div", { className: "page" }, h(ReviewPage, { state: state })),
      },
      {
        id: "chat",
        title: "Conversation",
        body: h(
          "div",
          { className: "page" },
          state.messages.map((message) =>
            h(Message, {
              key: message.id,
              message: message,
              open: Boolean(state.evidenceOpen[message.id]),
              onToggle: () => actions.toggleEvidence(message.id),
              report: message.report,
              state: state,
              actions: actions,
            })
          ),
          state.activity ? h("p", { className: "activity", role: "status" }, state.activity) : null,
          h(Suggestions, { suggestions: state.suggestions, onPick: actions.send })
        ),
      },
    ];
  }

  function Pager({ page, index, count, onPrevious, onNext }) {
    return h(
      "div",
      { className: "pager" },
      h("button", { type: "button", "aria-label": "Previous page", onClick: onPrevious, disabled: index === 0 }, "‹"),
      h("p", null, (page && page.title) || ""),
      h("button", { type: "button", "aria-label": "Next page", onClick: onNext, disabled: index >= count - 1 }, "›")
    );
  }

  const CONCERN = /\b(?:no returns?|non-?returnable|final sale|restock\w*|not covered|exclud\w*|void(?:ed|s)?|buyer pays|you pay|within\s+\d+\s*(?:days?|hours?)|\d+\s*-?\s*(?:days?|hours?)|must be|unworn|original (?:packaging|tags)|fee|cannot be returned|can't be returned|non-refundable|not as described|buyer protection)\b/i;

  function policyConcerns(state) {
    const rows = [];
    const seen = new Set();
    function add(label, text, source, retrieved) {
      const clean = String(text || "").replace(/\s+/g, " ").trim();
      if (clean.length < 20 || seen.has(clean) || /does not state a|no .+ sentence on this page|\$\{|cardName|keyboard shortcut|product summary presents/i.test(clean)) return;
      if (!retrieved && !CONCERN.test(clean)) return;
      seen.add(clean);
      rows.push({ label: label || "Policy", text: clean, source: source || "" });
    }
    ((state.summary && state.summary.bars) || []).forEach((bar) => {
      if (!/Returns|Warranty|Damage/.test(bar.label || "")) return;
      add(bar.label, bar.detail, "This page");
      (bar.points || []).forEach((point) => add(bar.label, point, "This page"));
    });
    (((state.outside || {}).policies) || []).forEach((policy) => {
      add(/return|refund/i.test(policy.title || policy.text || "") ? "Returns" : "Other policy", policy.text, policy.url || "", true);
    });
    (((state.dossier || {}).documents) || []).forEach((document) => {
      const label = /return|refund/i.test((document.title || "") + (document.excerpt || "")) ? "Returns" : "Other policy";
      add(label, document.excerpt, document.url || "");
    });
    return rows.slice(0, 6);
  }

  function PolicyConcerns({ state }) {
    const rows = policyConcerns(state);
    if (!rows.length) {
      const note = ((state.outside || {}).coverage || {}).policies || "No return or warranty passage was retrieved from this page or from other sites.";
      return h("article", { className: "section-page visual" }, h("h2", null, "Policy concerns"), h("p", { className: "hero" }, note));
    }
    return h(
      "article",
      { className: "section-page visual" },
      h("h2", null, "Policy concerns"),
      rows.map((row) =>
        h(
          "article",
          { className: "concern", key: row.label + row.text },
          h("span", null, row.label),
          h("p", null, row.text),
          row.source ? h("em", null, row.source) : null
        )
      )
    );
  }

  function carbonFigure(report) {
    const blocks = report && Array.isArray(report.blocks) ? report.blocks : [];
    for (let index = 0; index < blocks.length; index += 1) {
      const findings = blocks[index].type === "sustainability_report" ? blocks[index].findings || [] : [];
      for (let item = 0; item < findings.length; item += 1) {
        const finding = findings[item];
        if (finding.status === "verified" && /carbon|co2/i.test(String(finding.label || "") + String(finding.value || "")) && /\d/.test(String(finding.value || ""))) {
          return String(finding.value);
        }
      }
    }
    return "";
  }

  function RegistryNotes({ entries }) {
    if (!Array.isArray(entries) || !entries.length) return null;
    return h(
      "article",
      { className: "section-page" },
      h("h2", null, "Public registry"),
      entries.map((entry) =>
        h(
          "p",
          { key: entry.id || entry.title },
          h("strong", null, entry.title || "Earlier finding"),
          entry.detail ? " " + entry.detail : ""
        )
      )
    );
  }

  function Footprint({ footprint, figure }) {
    const estimate = footprint || {};
    const verified = Boolean((estimate.low && estimate.high) || figure);
    const label = estimate.coverage || estimate.productHeadline || estimate.headline || figure || "Product carbon footprint not independently verified.";
    return h(
      "article",
      { className: "section-page visual" },
      h(
        "div",
        { className: "footprint " + (verified ? "verified" : "open"), role: "img", "aria-label": label },
        h(
          "svg",
          { viewBox: "0 0 160 210", "aria-hidden": "true" },
          h("ellipse", { cx: "46", cy: "34", rx: "13", ry: "18" }),
          h("ellipse", { cx: "68", cy: "24", rx: "12", ry: "16" }),
          h("ellipse", { cx: "88", cy: "34", rx: "11", ry: "16" }),
          h("ellipse", { cx: "104", cy: "52", rx: "10", ry: "14" }),
          h("ellipse", { cx: "112", cy: "72", rx: "8", ry: "12" }),
          h("path", { d: "M48 86c-20 12-28 40-20 74 8 32 34 46 56 40 24-6 40-30 36-62-4-34-22-54-42-60-8-3-20 0-30 8z" })
        )
      ),
      h("p", { className: "foot-figure" }, estimate.low && estimate.high ? estimate.low + "–" + estimate.high : figure || "Not verified"),
      h("h2", null, "Footprint"),
      estimate.companyHeadline ? h("h3", null, "Company") : null,
      estimate.companyHeadline ? h("p", { className: "hero" }, estimate.companyHeadline) : null,
      h("h3", null, "This kind of product"),
      h("p", null, estimate.productHeadline || label),
      estimate.detail ? h("p", null, estimate.detail) : null,
      estimate.source && estimate.source.url
        ? h("a", { href: estimate.source.url, target: "_blank", rel: "noreferrer" }, estimate.source.title || "Outside source")
        : null
    );
  }

  function reviewGroups(state) {
    const product = [];
    const seller = [];
    const seen = new Set();
    function add(quote, source, url, image) {
      const clean = String(quote || "").replace(/\s+/g, " ").trim();
      if (clean.length < 12 || seen.has(clean)) return;
      if (/customer reviews help|help customers decide|was this review helpful|write a review|no customer reviews|be the first to/i.test(clean)) return;
      seen.add(clean);
      const row = { quote: clean, source: source || "Review", url: url || "", image: /^https?:/i.test(String(image || "")) ? image : "" };
      if (/\b(seller|sold by|customer service|shipping|merchant|this store|the shop|shop owner)\b/i.test(clean)) seller.push(row);
      else product.push(row);
    }
    (((state.dossier || {}).reviews) || []).forEach((review) => add(review.quote, review.source, review.url, review.image));
    (((state.outside || {}).reviews) || []).forEach((review) => add(review.quote, review.source, review.url, review.image));
    const reviewBar = ((state.summary && state.summary.bars) || []).find((bar) => bar.label === "Reviews");
    ((reviewBar && reviewBar.points) || []).forEach((quote) => add(quote, "This page", ""));
    const sellerRecord = (state.dossier || {}).seller || {};
    return {
      sellerName: sellerRecord.name || "",
      product: product.slice(0, 4),
      seller: seller.slice(0, 4),
    };
  }

  function ReviewCard({ review }) {
    return h(
      "article",
      { className: "review-card" },
      review.image ? h("img", { src: review.image, alt: "" }) : null,
      h("p", null, review.quote),
      review.url && !/^this page$/i.test(String(review.source || ""))
        ? h("a", { href: review.url, target: "_blank", rel: "noopener noreferrer" }, review.source || "Source")
        : null
    );
  }

  function ReviewPage({ state }) {
    const groups = reviewGroups(state);
    if (!groups.product.length && !groups.seller.length) {
      const note = ((state.outside || {}).coverage || {}).reviews || "No customer review excerpt was retrieved from other sites. Retailer help text is not treated as a review.";
      return h("article", { className: "section-page visual" }, h("h2", null, "Reviews"), h("p", { className: "hero" }, note));
    }
    return h(
      "article",
      { className: "section-page visual" },
      h("h2", null, "Reviews"),
      groups.product.length ? h("h3", null, "About the product") : null,
      groups.product.map((review) => h(ReviewCard, { key: review.quote, review: review })),
      groups.seller.length || groups.sellerName ? h("h3", null, "About the seller") : null,
      groups.sellerName ? h("p", null, "The page names the seller as " + groups.sellerName + ".") : null,
      groups.seller.map((review) => h(ReviewCard, { key: review.quote, review: review }))
    );
  }

  function Header({ state, actions }) {
    return h(
      "header",
      { className: "bar" },
      h(Mark, null),
      h(
        "div",
        { className: "titles" },
        h("p", { className: "name" }, "Unmasked"),
        state.textStatus ? h("p", { className: "status" }, state.textStatus) : null
      ),
      h("button", { type: "button", className: "icon", "aria-label": "Cart", onClick: actions.toggleCart }, "Cart"),
      h("button", { type: "button", className: "icon", "aria-label": state.expanded ? "Shrink" : "Expand", onClick: actions.toggleExpand }, state.expanded ? "Shrink" : "Expand"),
      h("button", { type: "button", className: "icon", "aria-expanded": state.menu ? "true" : "false", "aria-label": "Menu", onClick: actions.toggleMenu }, "Menu"),
      h("button", { type: "button", className: "icon", "aria-label": "Close", onClick: actions.close }, "Close")
    );
  }

  function Mark() {
    const src = typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.getURL
      ? chrome.runtime.getURL("icons/logo.jpeg")
      : "icons/logo.jpeg";
    return h("img", { className: "mark", src: src, alt: "Unmasked" });
  }

  function Reading({ state }) {
    const steps = state.readingSteps || [];
    const step = state.readingStep || 0;
    return h(
      "div",
      { className: "reading", role: "status" },
      h("div", { className: "scan", "aria-hidden": "true" }, h("span"), h("span"), h("span")),
      h("h2", null, "Pulling this product"),
      h("p", null, steps[step] || "Reading this page"),
      h(
        "ol",
        null,
        steps.map((label, index) => h("li", { key: label, className: index === step ? "on" : index < step ? "done" : "" }, label))
      )
    );
  }

  function Welcome({ state }) {
    const summary = state.summary;
    const title = (summary && summary.title) || "this product";
    return h(
      "div",
      { className: "welcome" },
      h("h2", null, "Welcome to Unmasked"),
      h("p", null, "Ask me anything about ", h("strong", null, title), "."),
    );
  }

  function SectionPage({ section }) {
    return h(
      "article",
      { className: "page section-page visual" },
      h("h2", null, section.title),
      section.chart ? h(ReviewChart, { chart: section.chart }) : null,
      section.text ? h("p", { className: "hero" }, section.text) : null,
      section.points && section.points.length
        ? h(
            "div",
            { className: "point-cards" },
            section.points.map((point) => h("p", { className: "point-card", key: point }, point))
          )
        : null
    );
  }

  function ReviewChart({ chart }) {
    const weighted = chart.negative * 2;
    const max = Math.max(chart.positive, weighted, 1);
    return h(
      "div",
      { className: "chart", role: "img", "aria-label": "Review balance, complaints counted twice" },
      h(ChartRow, { label: "Positive", tone: "positive", count: chart.positive, width: (chart.positive / max) * 100 }),
      h(ChartRow, { label: "Negative ×2", tone: "negative", count: weighted, width: (weighted / max) * 100 })
    );
  }

  function ChartRow({ label, count, width, tone }) {
    return h(
      "div",
      { className: "chart-row " + (tone || "") },
      h("span", null, label),
      h("span", { className: "track" }, h("span", { className: "fill " + (tone || ""), style: { width: Math.max(width, count ? 8 : 0) + "%" } })),
      h("span", { className: "count" }, String(count))
    );
  }

  function ProductRail({ label, products, onAdd, onWishlist, stacked }) {
    return h(
      "div",
      null,
      label ? h("p", { className: "rail-label" }, label) : null,
      h(
      "div",
      { className: "rail" + (stacked ? " stack" : ""), role: "list" },
      products.map((product) =>
        h(
          "article",
          { className: "card", role: "listitem", key: product.url || product.name },
          /^https?:/i.test(String(product.imageUrl || ""))
            ? h("img", { src: product.imageUrl, alt: "" })
            : h("span", { className: "photo" }, String(product.store || product.name || "•").slice(0, 1)),
          h(
            "h3",
            null,
            product.url
              ? h("a", { href: product.url, target: "_blank", rel: "noopener noreferrer" }, product.name)
              : product.name
          ),
          product.store || product.price || product.priceNote
            ? h(
                "p",
                null,
                [product.store, product.price ? "$" + product.price : product.priceNote].filter(Boolean).join(" · ")
              )
            : null,
          product.reviewScore || product.reviewNote
            ? h("p", null, product.reviewScore ? product.reviewScore + " out of 5" : product.reviewNote)
            : null,
          product.footprintLow && product.footprintHigh
            ? h("p", null, product.footprintLow + "–" + product.footprintHigh + " kg CO2e" + (product.footprintNote ? ". " + product.footprintNote : ""))
            : product.footprintNote
              ? h("p", null, product.footprintNote)
              : null,
          product.because ? h("p", { className: "why" }, product.because) : null,
          product.quotation || product.message ? h("p", { className: "why" }, product.quotation || product.message) : null,
          h("button", { type: "button", onClick: () => onAdd(product) }, "Add"),
          onWishlist ? h("button", { type: "button", onClick: () => onWishlist(product) }, "Wishlist") : null
        )
      )
      )
    );
  }

  function blockTitle(block) {
    if (block.type === "summary_card") return "What to know";
    if (block.type === "sustainability_report") return block.title || "Environmental analysis";
    if (block.type === "missing_evidence") return "Carbon footprint";
    if (block.type === "source_list") return "Sources";
    if (block.type === "follow_up") return "Ask next";
    if (block.type === "suggested_action") return "What you can do";
    return "Report";
  }

  function renderBlock(block, report, state, actions) {
    if (block.type === "summary_card") return h(SummaryCard, { block: block });
    if (block.type === "sustainability_report") return h(SustainabilityReport, { block: block, report: report });
    if (block.type === "missing_evidence") return h(MissingEvidence, { block: block });
    if (block.type === "source_list") return h(SourceList, { block: block, report: report });
    if (block.type === "follow_up") return h(FollowUp, { question: block.question, onAsk: actions.send });
    if (block.type === "suggested_action") return h(ActionList, { actions: [block.action], state: state, run: actions });
    return null;
  }

  function SummaryCard({ block }) {
    const unverified = /unverified|not verified/i.test(String(block.verdict || ""));
    return h(
      "article",
      { className: "section-page visual" },
      h("div", { className: "mark-lg " + (unverified ? "open" : "solid"), "aria-hidden": "true" }, unverified ? "–" : "✓"),
      h("h2", null, "What to know"),
      h("p", { className: "hero" }, block.verdict),
      block.why ? h("p", { className: "why-line" }, block.why) : null
    );
  }

  function statusLabel(status) {
    if (status === "verified") return "Independent source";
    if (status === "manufacturer_claim") return "Manufacturer claim";
    if (status === "contradicted") return "Contradicted";
    if (status === "unavailable") return "Unavailable";
    return "Not enough evidence";
  }

  function SustainabilityReport({ block, report }) {
    const findings = Array.isArray(block.findings) ? block.findings.slice(0, 3) : [];
    return h(
      "article",
      { className: "section-page visual" },
      h("h2", null, block.title || "Environmental analysis"),
      h("p", { className: "status-pill " + (block.status || "") }, statusLabel(block.status)),
      findings.length
        ? h(
            "div",
            { className: "tiles" },
            findings.map((finding) => {
              const sourceId = finding.sourceIds && finding.sourceIds[0];
              const source = sourceId && report ? (report.sources || []).find((item) => item.id === sourceId) : null;
              return h(
                "article",
                { className: "tile " + (finding.status || ""), key: finding.label + finding.value },
                h("span", { className: "tile-label" }, finding.label),
                h("strong", null, finding.value),
                h("em", null, statusLabel(finding.status)),
                source
                  ? h("a", { href: source.url, target: "_blank", rel: "noopener noreferrer" }, source.domain)
                  : null
              );
            })
          )
        : h("p", { className: "hero" }, "No material or certification finding was retrieved.")
    );
  }

  function MissingEvidence({ block }) {
    return h(
      "article",
      { className: "section-page visual" },
      h("div", { className: "ring unverified", role: "img", "aria-label": block.reason || "Footprint not estimated" }, h("strong", null, "—")),
      h("h2", null, "Carbon footprint"),
      h("p", { className: "hero" }, block.reason || "The page did not name a material, so the footprint is not estimated."),
      h("p", null, "The estimate uses the material and the product type when the page names them.")
    );
  }

  function SourceList({ block, report }) {
    const ids = Array.isArray(block.sourceIds) ? block.sourceIds : [];
    const sources = ids
      .map((id) => (report.sources || []).find((source) => source.id === id))
      .filter(Boolean);
    return h(
      "article",
      { className: "section-page" },
      h("h2", null, "Sources"),
      sources.length
        ? sources.map((source) => h(SourcePreview, { key: source.id, source: source }))
        : h("p", null, "No source was retrieved for this product.")
    );
  }

  function sourceClassLabel(sourceClass) {
    if (sourceClass === "independent_product") return "Independent product evidence";
    if (sourceClass === "manufacturer") return "Manufacturer information";
    if (sourceClass === "customer_review") return "Customer review";
    if (sourceClass === "certification") return "Certification evidence";
    return "General background research";
  }

  function SourcePreview({ source }) {
    const letter = String(source.domain || "?").replace(/^www\./, "").slice(0, 1).toUpperCase();
    return h(
      "article",
      { className: "source-card" },
      h(
        "div",
        { className: "source-row" },
        h("span", { className: "monogram", "aria-hidden": "true" }, letter),
        h(
          "div",
          null,
          h("strong", null, source.title || source.domain),
          h("span", null, source.domain),
          h("em", null, sourceClassLabel(source.sourceClass))
        )
      ),
      source.excerpt ? h("p", null, source.excerpt) : null,
      h("a", { href: source.url, target: "_blank", rel: "noopener noreferrer" }, "View source")
    );
  }

  function FollowUp({ question, onAsk }) {
    if (!question) return null;
    return h(
      "article",
      { className: "section-page" },
      h("h2", null, "Ask next"),
      h("button", { type: "button", className: "solid", onClick: () => onAsk(question) }, question)
    );
  }

  function ActionList({ actions, state, run }) {
    const usable = (actions || []).filter((action) => actionReady(action, state));
    return h(
      "article",
      { className: "section-page" },
      h("h2", null, "What you can do"),
      usable.length
        ? h(
            "div",
            { className: "actions" },
            usable.map((action) => h(ActionButton, { key: action.type + (action.url || action.question || action.label), action: action, state: state, run: run }))
          )
        : h("p", null, "No action is available for this product yet.")
    );
  }

  function actionReady(action, state) {
    if (!action) return false;
    if (action.type === "save_product") return Boolean(state.pageProduct && state.pageProduct.url);
    if (action.type === "compare_alternatives" || action.type === "ask_follow_up") return true;
    if (action.type === "open_source" || action.type === "open_product") return /^https?:/i.test(String(action.url || ""));
    return false;
  }

  function ActionButton({ action, state, run }) {
    if (action.type === "open_source" || action.type === "open_product") {
      return h("a", { className: "solid link", href: action.url, target: "_blank", rel: "noopener noreferrer" }, action.label || "Open");
    }
    const onClick = () => {
      if (action.type === "compare_alternatives") run.send("Is there a greener option?");
      else if (action.type === "ask_follow_up") run.send(action.question);
      else if (action.type === "save_product" && state.pageProduct) run.wishlist(state.pageProduct);
    };
    return h("button", { type: "button", className: "solid", onClick: onClick }, action.label || "Continue");
  }

  function Message({ message, open, onToggle, report, state, actions }) {
    const evidence = message.evidence || [];
    return h(
      "div",
      { className: "message " + message.role },
      h("p", null, message.text),
      report && message.role === "agent"
        ? report.blocks.map((block, index) => h("div", { key: block.type + index, className: "inline-block" }, renderBlock(block, report, state, actions)))
        : null,
      evidence.length
        ? h(
            "div",
            { className: "evidence" },
            h(
              "button",
              { type: "button", "aria-expanded": open ? "true" : "false", onClick: onToggle },
              open ? "Hide evidence" : "Evidence and citations"
            ),
            open
              ? h(
                  "ul",
                  null,
                  evidence.map((item) =>
                    h(
                      "li",
                      { key: item.title + item.text },
                      h("strong", null, item.title),
                      " ",
                      item.text,
                      item.url ? h("a", { href: item.url, target: "_blank", rel: "noopener noreferrer" }, " Source") : null
                    )
                  )
                )
              : null
          )
        : null
    );
  }

  function Suggestions({ suggestions, onPick }) {
    if (!suggestions.length) return null;
    return h(
      "div",
      { className: "suggestions" },
      suggestions.map((suggestion) =>
        h("button", { type: "button", key: suggestion, onClick: () => onPick(suggestion) }, suggestion)
      )
    );
  }

  function CartSheet({ state, actions }) {
    return h(
      "div",
      { className: "sheet" },
      h("p", { className: "sheet-title" }, "Cart"),
      state.cart.length
        ? h(
            "ul",
            null,
            state.cart.map((item) => h("li", { key: item.url }, item.store + " · " + item.name + " · $" + item.price))
          )
        : h("p", null, "Nothing in the cart yet."),
      h("button", { type: "button", className: "solid", onClick: actions.purchase, disabled: !state.cart.length }, "Purchase all")
    );
  }

  function MenuSheet({ state, actions }) {
    return h(
      "div",
      { className: "sheet menu", role: "menu" },
      h("button", { type: "button", "aria-pressed": state.inboxMode ? "false" : "true", onClick: () => actions.setInbox(false) }, "This page"),
      h("button", { type: "button", "aria-pressed": state.inboxMode ? "true" : "false", onClick: () => actions.setInbox(true) }, "Messages"),
      h("button", { type: "button", onClick: actions.startCall }, "Call")
    );
  }

  function CallSheet({ call, onHangUp }) {
    return h(
      "div",
      { className: "sheet call" },
      h("p", { className: "sheet-title" }, call.status),
      call.body ? h("p", null, call.body) : null,
      h("button", { type: "button", onClick: onHangUp }, "Hang up")
    );
  }

  function Composer({ placeholder, onSend }) {
    const [value, setValue] = React.useState("");
    function submit(event) {
      event.preventDefault();
      const text = value.trim();
      if (!text) return;
      setValue("");
      onSend(text);
    }
    return h(
      "form",
      { className: "composer", onSubmit: submit },
      h("label", { className: "visually-hidden", htmlFor: "unmasked-question" }, placeholder),
      h("input", {
        id: "unmasked-question",
        name: "question",
        value,
        placeholder,
        autoComplete: "off",
        onChange: (event) => setValue(event.target.value),
      }),
      h("button", { type: "submit" }, "Send")
    );
  }

  const css = [
    ".host, .dock, .panel, button, input { font-family: \"Avenir Next\", \"Segoe UI\", \"Helvetica Neue\", sans-serif; }",
    ".dock { position: fixed; right: 16px; bottom: 16px; z-index: 2147483646; display: flex; justify-content: flex-end; pointer-events: none; }",
    ".dock.open { top: 0; right: 0; bottom: 0; }",
    ".launcher, .panel, .composer, .card button, .sheet button, .icon, .pager button { pointer-events: auto; }",
    ".launcher { display: inline-flex; align-items: center; gap: 12px; border: 0; border-radius: 999px; background: linear-gradient(135deg, #1f6b45, #16382c 55%, #2b2418); color: #fff; padding: 8px 18px 8px 8px; cursor: pointer; box-shadow: 0 12px 32px rgba(31,107,69,0.35); font: inherit; }",
    ".launcher-copy { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.15; text-align: left; }",
    ".launcher-copy strong { font-size: 15px; font-weight: 700; }",
    ".launcher-copy span { font-size: 12px; opacity: 0.72; }",
    ".panel { width: min(400px, calc(100vw - 24px)); height: min(860px, 88vh); max-height: min(860px, 88vh); display: flex; flex-direction: column; color: #f7f4ee; background: linear-gradient(180deg, #1c3d32 0%, #243028 38%, #2a2420 100%); border-radius: 28px; box-shadow: 0 18px 50px rgba(0,0,0,0.35); overflow: hidden; }",
    ".dock.open .panel { width: min(440px, 100vw); height: 100vh; max-height: 100vh; border-radius: 0; border-left: 1px solid rgba(244,210,122,0.35); }",
    ".panel.expanded { width: min(520px, 100vw); }",
    ".views { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; padding: 0 14px 8px; }",
    ".views button { border: 0; border-radius: 999px; min-height: 36px; background: rgba(247,244,238,0.08); color: inherit; cursor: pointer; font: inherit; font-size: 13px; font-weight: 700; }",
    ".views button[aria-pressed='true'] { background: #f4d27a; color: #1c3d32; }",
    ".login { display: flex; flex-direction: column; gap: 10px; padding: 8px 4px 24px; }",
    ".login input { min-height: 44px; border: 0; border-radius: 12px; padding: 0 12px; font: inherit; }",
    ".login button { min-height: 42px; border: 0; border-radius: 999px; font: inherit; font-weight: 700; cursor: pointer; }",
    ".login button[type='submit'] { background: #f4d27a; color: #1c3d32; }",
    ".login button[type='button'] { background: transparent; color: inherit; }",
    ".bar { display: flex; align-items: center; gap: 8px; padding: 14px 14px 8px; }",
    ".mark { width: 36px; height: 36px; border-radius: 50%; object-fit: cover; flex: 0 0 auto; box-shadow: 0 0 0 4px rgba(244,210,122,0.25); }",
    ".panel.reading .mark { animation: pulse 1.2s ease-in-out infinite; }",
    ".spark { font-size: 16px; line-height: 1; }",
    ".titles { flex: 1; min-width: 0; }",
    ".name { margin: 0; font-size: 16px; font-weight: 700; white-space: nowrap; }",
    ".status, .scoreline, .why, .activity, .sheet p, .message p { margin: 0; }",
    ".status { font-size: 12px; opacity: 0.75; }",
    ".icon { border: 0; background: transparent; color: inherit; font: inherit; font-size: 12px; cursor: pointer; padding: 6px; }",
    ".stage { flex: 1; min-height: 0; overflow: hidden; display: flex; }",
    ".page { flex: 1; min-height: 0; overflow: auto; padding: 20px 22px 12px; display: flex; flex-direction: column; gap: 14px; animation: rise 0.35s ease; }",
    ".section-page h2 { margin: 0; font-size: 26px; line-height: 1.15; letter-spacing: -0.03em; }",
    ".why-line { color: #f4d27a; }",
    ".visual { align-items: stretch; }",
    ".hero { margin: 0; padding: 16px; border-radius: 20px; background: rgba(0,0,0,0.28); font-size: 20px; line-height: 1.35; }",
    ".mark-lg { width: 72px; height: 72px; border-radius: 50%; display: grid; place-items: center; font-size: 32px; font-weight: 700; }",
    ".mark-lg.open { background: rgba(255,138,91,0.18); color: #ff8a5b; box-shadow: inset 0 0 0 3px #ff8a5b; }",
    ".mark-lg.solid { background: #3dbe7a; color: #10241c; }",
    ".tiles { display: flex; flex-direction: column; gap: 10px; }",
    ".tile { display: flex; flex-direction: column; gap: 4px; padding: 14px; border-radius: 18px; background: #163028; border-top: 4px solid #f4d27a; }",
    ".tile.verified { border-top-color: #3dbe7a; }",
    ".tile.manufacturer_claim { border-top-color: #7eb6ff; }",
    ".tile.insufficient_evidence { border-top-color: #ff8a5b; }",
    ".tile-label, .tile em, .source-row em, .source-row span { font-style: normal; font-size: 12px; color: rgba(247,244,238,0.72); }",
    ".tile strong { font-size: 22px; line-height: 1.2; }",
    ".ring { width: 168px; height: 168px; margin: 8px auto 0; border-radius: 50%; display: grid; place-items: center; background: repeating-conic-gradient(#ff8a5b 0 10deg, rgba(255,255,255,0.08) 10deg 24deg); }",
    ".ring strong { width: 124px; height: 124px; border-radius: 50%; display: grid; place-items: center; background: #1c3d32; font-size: 42px; color: #ff8a5b; }",
    ".point-cards { display: flex; flex-direction: column; gap: 8px; }",
    ".point-card { margin: 0; padding: 12px 14px; border-radius: 16px; background: rgba(126,182,255,0.12); border-left: 3px solid #7eb6ff; }",
    ".source-row { display: flex; gap: 12px; align-items: center; }",
    ".source-row div { display: flex; flex-direction: column; gap: 2px; min-width: 0; }",
    ".monogram { width: 42px; height: 42px; border-radius: 14px; display: grid; place-items: center; background: #f4d27a; color: #1c3d32; font-weight: 700; flex: 0 0 auto; }",
    ".chart-row { grid-template-columns: 92px 1fr 28px; font-size: 13px; }",
    ".track { height: 14px; }",
    ".status-pill { display: inline-flex; align-self: flex-start; margin: 0; padding: 4px 10px; border-radius: 999px; background: rgba(61,190,122,0.18); color: #b7f0d0; font-size: 12px; font-weight: 700; }",
    ".findings { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 10px; }",
    ".findings li { display: flex; flex-direction: column; gap: 4px; padding: 12px; border-radius: 16px; background: rgba(12, 28, 24, 0.55); }",
    ".findings strong { font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; color: #f4d27a; }",
    ".findings em { font-style: normal; font-size: 12px; color: rgba(247,244,238,0.72); }",
    ".findings a, .source-card a, .link { color: #b7f0d0; }",
    ".source-card { background: rgba(12, 28, 24, 0.55); border-radius: 16px; padding: 10px 12px; }",
    ".source-card summary { cursor: pointer; font-weight: 700; }",
    ".source-card p { margin: 8px 0 0; font-size: 14px; line-height: 1.4; }",
    ".actions { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; }",
    ".link { display: inline-block; text-decoration: none; }",
    ".inline-block { margin-top: 12px; }",
    ".pager { display: grid; grid-template-columns: 40px 1fr 40px; align-items: center; gap: 8px; padding: 0 14px 8px; }",
    ".pager p { margin: 0; text-align: center; font-weight: 700; color: #f4d27a; }",
    ".pager span { display: block; margin-top: 2px; font-size: 12px; font-weight: 600; color: rgba(247,244,238,0.72); }",
    ".concern, .review-card { margin: 0 0 10px; padding: 12px 14px; border-radius: 16px; background: rgba(247,244,238,0.08); }",
    ".review-card img { width: 100%; height: 160px; object-fit: cover; border-radius: 12px; margin-bottom: 10px; background: #111; }",
    ".concern { border: 1px solid rgba(255,138,91,0.7); }",
    ".concern span, .review-card em { display: block; margin-top: 6px; font-style: normal; font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: #ff8a5b; }",
    ".review-card em { color: rgba(247,244,238,0.72); letter-spacing: 0; text-transform: none; }",
    ".section-page h3 { margin: 16px 0 8px; font-size: 16px; }",
    ".footprint { width: 150px; margin: 8px auto 0; }",
    ".footprint svg { width: 150px; height: 196px; display: block; }",
    ".footprint.open svg { fill: none; stroke: #ff8a5b; stroke-width: 3; stroke-dasharray: 7 6; }",
    ".footprint.verified svg { fill: #3dbe7a; stroke: #f4d27a; stroke-width: 2; }",
    ".foot-figure { margin: 4px 0 8px; text-align: center; font-size: 28px; font-weight: 700; }",
    ".pager button { width: 40px; height: 40px; border: 0; border-radius: 50%; background: #3dbe7a; color: #10241c; font-size: 24px; line-height: 1; cursor: pointer; }",
    ".pager button:disabled { opacity: 0.35; cursor: default; }",
    ".welcome h2 { margin: 8px 0 6px; font-size: 28px; line-height: 1.15; letter-spacing: -0.03em; }",
    ".welcome p, .message p { font-size: 16px; line-height: 1.45; }",
    ".overview { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }",
    ".overview h3, .rail-label { margin: 4px 0 0; font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: #f4d27a; }",
    ".overview details { background: rgba(12, 28, 24, 0.55); border-radius: 16px; padding: 10px 12px; border-left: 3px solid #3dbe7a; }",
    ".overview details:nth-of-type(2) { border-left-color: #7eb6ff; }",
    ".overview details:nth-of-type(3) { border-left-color: #ff8a5b; }",
    ".overview details:nth-of-type(4) { border-left-color: #f4d27a; }",
    ".overview summary { cursor: pointer; font-weight: 700; }",
    ".overview p, .overview li { margin: 6px 0 0; font-size: 14px; line-height: 1.45; }",
    ".chart { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }",
    ".chart-row { display: grid; grid-template-columns: 92px 1fr 24px; gap: 8px; align-items: center; font-size: 12px; }",
    ".track { height: 8px; border-radius: 999px; background: rgba(255,255,255,0.12); overflow: hidden; }",
    ".fill { display: block; height: 100%; border-radius: 999px; background: #f4d27a; }",
    ".fill.positive { background: #3dbe7a; }",
    ".fill.negative { background: #ff8a5b; }",
    ".count { text-align: right; font-variant-numeric: tabular-nums; }",
    ".rail { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 4px; scroll-snap-type: x mandatory; }",
    ".rail.stack { flex-direction: column; overflow: visible; }",
    ".rail.stack .card { flex: none; width: auto; }",
    ".card { flex: 0 0 148px; scroll-snap-align: start; background: #163028; border-radius: 22px; padding: 10px; border: 1px solid rgba(61,190,122,0.35); }",
    ".card img, .photo { width: 100%; height: 108px; object-fit: cover; border-radius: 16px; background: #111; display: flex; align-items: center; justify-content: center; font-size: 28px; }",
    ".card h3 { margin: 8px 0 0; font-size: 14px; font-weight: 600; line-height: 1.3; max-height: 2.6em; overflow: hidden; }",
    ".card p { margin: 4px 0 0; font-size: 12px; line-height: 1.35; opacity: 0.85; }",
    ".why { max-height: 3.9em; overflow: hidden; }",
    ".card button, .sheet button, .suggestions button { font: inherit; cursor: pointer; }",
    ".card button, .solid { margin-top: 8px; margin-right: 6px; border: 0; border-radius: 999px; background: #f4d27a; color: #1c3d32; padding: 6px 10px; }",
    ".card button:last-child { background: #3dbe7a; }",
    ".message.you { align-self: flex-end; max-width: 88%; background: #1f4d8a; border-radius: 18px; padding: 12px 14px; }",
    ".message.agent { align-self: stretch; }",
    ".message.you p, .message.agent p { white-space: pre-wrap; }",
    ".evidence { margin-top: 8px; }",
    ".evidence button, .suggestions button, .sheet button { border: 1px solid rgba(255,255,255,0.28); background: transparent; color: inherit; border-radius: 999px; padding: 6px 10px; font-size: 13px; }",
    ".evidence ul, .sheet ul { margin: 8px 0 0; padding-left: 18px; font-size: 13px; line-height: 1.4; }",
    ".evidence a { color: inherit; }",
    ".suggestions { display: flex; flex-wrap: wrap; gap: 8px; }",
    ".suggestions button:nth-child(3n+1) { border-color: #3dbe7a; color: #b7f0d0; }",
    ".suggestions button:nth-child(3n+2) { border-color: #7eb6ff; color: #d6e8ff; }",
    ".suggestions button:nth-child(3n) { border-color: #f4d27a; color: #f4d27a; }",
    ".activity { font-size: 13px; opacity: 0.75; }",
    ".sheet { margin: 0 14px 8px; padding: 10px 12px; border-radius: 16px; background: #1c1c1c; }",
    ".sheet-title { font-weight: 700; margin-bottom: 6px; }",
    ".menu { display: flex; gap: 8px; flex-wrap: wrap; }",
    ".menu button[aria-pressed='true'] { background: #fff; color: #1c1c1c; }",
    ".composer { display: flex; gap: 8px; align-items: center; margin: 8px 14px 14px; padding: 4px 4px 4px 16px; border: 1px solid rgba(255,255,255,0.35); border-radius: 999px; }",
    ".composer input { flex: 1; min-width: 0; border: 0; background: transparent; color: inherit; font: inherit; font-size: 16px; padding: 10px 0; }",
    ".composer input:focus { outline: none; }",
    ".composer input::placeholder { color: rgba(247,244,238,0.62); }",
    ".composer button { border: 0; border-radius: 999px; background: #3dbe7a; color: #10241c; font: inherit; font-weight: 700; padding: 8px 14px; cursor: pointer; }",
    ".reading { padding: 28px 8px 12px; }",
    ".reading h2 { margin: 18px 0 8px; font-size: 28px; letter-spacing: -0.03em; }",
    ".reading p { margin: 0 0 16px; color: #f4d27a; }",
    ".reading ol { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }",
    ".reading li { padding: 10px 12px; border-radius: 14px; background: rgba(0,0,0,0.2); color: rgba(247,244,238,0.55); }",
    ".reading li.on { color: #fff; background: #1f6b45; animation: rise 0.45s ease; }",
    ".reading li.done { color: #b7f0d0; }",
    ".scan { position: relative; height: 92px; border-radius: 18px; overflow: hidden; background: rgba(0,0,0,0.25); }",
    ".scan span { position: absolute; left: -40%; width: 40%; height: 100%; background: linear-gradient(90deg, transparent, rgba(61,190,122,0.15), #f4d27a, rgba(126,182,255,0.2), transparent); animation: sweep 1.6s ease-in-out infinite; }",
    ".scan span:nth-child(2) { animation-delay: 0.25s; opacity: 0.7; }",
    ".scan span:nth-child(3) { animation-delay: 0.5s; opacity: 0.45; }",
    "@keyframes sweep { from { transform: translateX(0); } to { transform: translateX(380%); } }",
    "@keyframes pulse { 50% { transform: scale(1.08); box-shadow: 0 0 0 8px rgba(61,190,122,0.28); } }",
    "@keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }",
    ".visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }",
    "@media (max-width: 640px) { .dock { right: 8px; left: 8px; bottom: 8px; } .panel, .panel.expanded { width: 100%; border-radius: 22px; } .welcome h2 { font-size: 24px; } }",
  ].join("\n");

  function mount(shadow) {
    const style = document.createElement("style");
    style.textContent = css;
    const node = document.createElement("div");
    node.className = "host";
    shadow.append(style, node);
    const root = ReactDOM.createRoot(node);
    return {
      render(state, actions) {
        root.render(h(ChatView, { state, actions }));
      },
    };
  }

  window.UnmaskedChat = { mount, acceptReport };
})();
