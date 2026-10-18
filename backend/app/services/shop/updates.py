"""A sign-in update built from this shopper's purchases, then handed to Photon."""

import re

from backend.app.services.catalog.identity import known_kind
from backend.app.services.shop.cart import contact
from backend.app.services.shop.taste import load_taste, personalize

_PROFILE = re.compile(
    r"\b(?:my name|what'?s my name|who am i|about me|my (?:profile|account|email|number|phone)|what do you know about me)\b",
    re.IGNORECASE,
)
_RETURNED = re.compile(
    r"\b(?:what did i return|items? i returned|my returns?|sent back|"
    r"brands? i (?:avoid|returned)|which (?:ones?|items?) did i return)\b",
    re.IGNORECASE,
)
_TASTE = re.compile(
    r"\b(?:my (?:taste|brands?|colors?)|what (?:do i|did i) (?:like|keep)|recommend)\b",
    re.IGNORECASE,
)
_FIND = re.compile(
    r"\b(?:find|show|search|look(?:ing)? for|similar|alternative|other (?:stores?|products?)|cheaper|greener|buy|shop for)\b",
    re.IGNORECASE,
)
_WEB = re.compile(
    r"\b(?:https?://|www\.|policy|review|warranty|return window|materials?|compare|best|price of)\b",
    re.IGNORECASE,
)


def account_update(user_id: str, name: str = "") -> dict:
    """Describe this shopper's products and what to look at next."""
    orders = _orders(user_id)
    taste = load_taste(user_id)
    return {"text": _text(name, orders, taste), "products": _products(orders, taste)}


def deliver_update(user_id: str, name: str = "", phone: str = "") -> dict:
    """Build the update and text it to the mobile number on this account."""
    payload = account_update(user_id, name)
    from backend.app.integrations.photon_line import send_intro

    text = (
        "Welcome to Unmasked. "
        + payload["text"]
        + " Text this number with a question, a photo, or ask about an order."
    )
    result = send_intro(text, phone) or {}
    payload["sent"] = bool(result.get("sent"))
    payload["reason"] = "" if payload["sent"] else str(result.get("reason") or "Photon did not send the welcome text.")
    return payload


def sms_reply(
    question: str,
    phone: str = "",
    picture: bool = False,
    image: bytes | None = None,
    image_mime: str = "",
) -> str:
    """Answer an inbound text or product photo from the shopper's profile and the web."""
    from backend.app.services.shop.accounts import user_by_phone
    from backend.app.services.shop.cart import orders_answer

    user = user_by_phone(phone) or {}
    user_id = str(user.get("id") or "")
    name = str(user.get("name") or "")
    asked = " ".join(str(question or "").split())
    has_image = bool(image)
    if asked.lower() in {"hi", "hello", "hey", "ping", "start"} or (not asked and not picture and not has_image):
        update = account_update(user_id, name) if user_id else {
            "text": "Sign in on the extension with this mobile number so I can see your orders."
        }
        return _pack(
            "Welcome to Unmasked",
            update["text"],
            "Ask about an order, a return, a product, or send a product photo.",
        )
    if not user_id:
        return _pack(
            "Sign in on the extension with this mobile number so I can see your name, orders, and taste.",
        )

    profile = _shopper_profile(user)
    if has_image or picture:
        pictured = _picture_search_answer(image, image_mime, asked, profile) if has_image else None
        if pictured:
            return pictured
        if picture and not has_image:
            return _pack(
                "Photo received",
                "I could not download that image from the message yet. Send it again, or name the product to search.",
            )
        if has_image:
            return _pack(
                "Photo received",
                "I could not tell what product that is. Try a clearer shot of the item or label.",
            )

    if _PROFILE.search(asked):
        return _profile_answer(profile)
    if _RETURNED.search(asked):
        return _returns_answer(profile)
    if _TASTE.search(asked) and not _FIND.search(asked):
        return _taste_answer(profile)

    if _FIND.search(asked) or paired_item_safe(asked):
        found = _product_search_answer(asked, profile)
        if found:
            return found

    remembered = orders_answer(asked, user_id=user_id) if asked else None
    if remembered:
        return remembered

    # Web / compare / policy questions use live search; do not pin them to a kept order name.
    if asked and _WEB.search(asked):
        reply = _companion_answer(asked, profile)
        if reply:
            return reply

    named = _order_named_answer(asked, profile)
    if named:
        return named

    if asked:
        reply = _companion_answer(asked, profile)
        if reply:
            return reply

    update = account_update(user_id, name)
    if asked:
        return _pack(
            update["text"],
            "Ask about an order, a return, or name a product and I will look online.",
        )
    return update["text"]


def _pack(*parts: str) -> str:
    """Join reply sections with blank lines so iMessage stays scannable."""
    blocks = []
    for part in parts:
        text = str(part or "").strip()
        if text:
            blocks.append(text)
    return "\n\n".join(blocks)


def paired_item_safe(question: str) -> bool:
    from backend.app.services.shop.products import paired_item

    return paired_item(question, "") is not None


def _shopper_profile(user: dict) -> dict:
    user_id = str(user.get("id") or "")
    orders = _orders(user_id)
    taste = load_taste(user_id) if user_id else {"brands": [], "colors": [], "avoid": []}
    kept = []
    returned = []
    for order in orders:
        row = {
            "name": order.product_name,
            "store": order.store or "",
            "price": order.price or "",
            "status": order.delivery_status or "saved",
            "url": str(order.product_url or ""),
        }
        if _returned(order):
            returned.append(row)
        else:
            kept.append(row)
    return {
        "id": user_id,
        "name": str(user.get("name") or ""),
        "email": str(user.get("email") or ""),
        "phone": str(user.get("phone") or ""),
        "kept": kept,
        "returned": returned,
        "taste": taste,
    }


def _profile_answer(profile: dict) -> str:
    name = profile.get("name") or "there"
    email = profile.get("email") or "no email on file"
    phone = profile.get("phone") or "no mobile on file"
    kept = len(profile.get("kept") or [])
    returned = len(profile.get("returned") or [])
    brands = ", ".join((profile.get("taste") or {}).get("brands") or []) or "none yet"
    return "\n".join(
        [
            "Your profile",
            "",
            f"Name: {name}",
            f"Email: {email}",
            f"Mobile: {phone}",
            "",
            f"Kept purchases: {kept}",
            f"Returns: {returned}",
            f"Brands you keep: {brands}",
        ]
    )


def _returns_answer(profile: dict) -> str:
    returned = profile.get("returned") or []
    avoid = list((profile.get("taste") or {}).get("avoid") or [])
    if not returned and not avoid:
        return "Your returns\n\nYou have not marked any returns yet.\nReturned brands will stay off similar-product suggestions."
    lines = ["Your returns", ""]
    if returned:
        lines.append("Returned items")
        for item in returned[:4]:
            lines.append(f"• {item['name']}")
        lines.append("")
    if avoid:
        lines.append("Brands to avoid")
        lines.append("• " + ", ".join(avoid))
    return "\n".join(lines).rstrip()


def _taste_answer(profile: dict) -> str:
    taste = profile.get("taste") or {}
    brands = ", ".join(taste.get("brands") or []) or "none yet"
    colors = ", ".join(taste.get("colors") or []) or "none yet"
    avoid = ", ".join(taste.get("avoid") or []) or "none"
    return "\n".join(
        [
            "Your taste",
            "",
            f"Brands you keep: {brands}",
            f"Colors you keep: {colors}",
            f"Avoid: {avoid}",
        ]
    )


_GENERIC_ORDER_WORDS = {
    "with",
    "from",
    "plus",
    "wide",
    "women",
    "womens",
    "men",
    "mens",
    "jacket",
    "coat",
    "shoe",
    "shoes",
    "sneaker",
    "sneakers",
    "tent",
    "tents",
}


def _order_named_answer(question: str, profile: dict) -> str | None:
    asked = question.lower()
    for item in list(profile.get("kept") or []) + list(profile.get("returned") or []):
        name = str(item.get("name") or "")
        if not name:
            continue
        lowered = name.lower()
        words = [
            word
            for word in re.findall(r"[a-z0-9]{4,}", lowered)
            if word not in _GENERIC_ORDER_WORDS
        ]
        # Need the full product name, or at least two distinctive tokens (e.g. "torrentshell").
        if lowered in asked or (words and sum(1 for word in words[:5] if word in asked) >= 2) or (
            words and words[0] in asked and len(words[0]) >= 7
        ):
            status = item.get("status") or "saved"
            store = item.get("store") or "the store"
            price = f" (${item['price']})" if item.get("price") else ""
            return f"{name} from {store}{price} is {status.lower()}."
    return None


_FIND_NOISE = re.compile(
    r"\b(?:find|show|search|look(?:ing)? for|similar|alternative|other (?:stores?|products?)|"
    r"cheaper|greener|buy|shop for|where|else|can|i|me|a|an|some|please|online)\b",
    re.IGNORECASE,
)


def _picture_search_answer(image: bytes | None, image_mime: str, caption: str, profile: dict) -> str | None:
    """Identify a product in a photo and return live store listings."""
    if not image:
        return None
    from backend.app.integrations.openai_client import OpenAIClient
    from backend.app.services.shop.guard import gate
    from backend.app.services.shop.photo import prepare_image

    blocked = gate(caption or "find this product")
    if blocked is not None:
        return blocked
    ready, ready_mime = prepare_image(image, image_mime or "image/jpeg")
    if not ready:
        return None
    info = {}
    try:
        info = OpenAIClient().identify_product(ready, ready_mime or "image/jpeg") or {}
    except Exception as exc:
        print("photo identify failed:", type(exc).__name__, flush=True)
        info = {}
    query = " ".join(str(info.get("query") or info.get("name") or info.get("kind") or "").split())
    if caption and _FIND.search(caption):
        extras = " ".join(_FIND_NOISE.sub(" ", caption).split())
        if extras and extras.lower() not in query.lower():
            query = f"{extras} {query}".strip() if query else extras
    if not query and caption:
        # Last resort: search on the caption words when vision is blank.
        query = " ".join(_FIND_NOISE.sub(" ", caption).split())
    if not query:
        return None
    label = str(info.get("name") or query).strip()
    brand = str(info.get("brand") or "").strip()
    found = _product_search_answer(f"find {query}", profile)
    if not found:
        return _pack(
            "From your photo",
            f"That looks like: {label}" + (f"\nBrand: {brand}" if brand else ""),
            "No clear store listing came back just now.",
        )
    intro = f"From your photo\n\nThat looks like: {label}"
    if brand:
        intro += f"\nBrand: {brand}"
    return _pack(intro, found)


def _product_search_answer(question: str, profile: dict) -> str | None:
    from backend.app.services.shop.products import find_products, loose_products, paired_item

    pair = paired_item(question, "")
    item = ""
    prefix = ""
    if pair:
        item, prefix = pair
    else:
        item = " ".join(_FIND_NOISE.sub(" ", question).split())
    if not item:
        kept = profile.get("kept") or []
        if kept:
            item = known_kind(kept[0]["name"]) or kept[0]["name"]
    if not item:
        return None
    try:
        products = find_products(item, query_prefix=prefix)
        if len(products) < 3:
            products = products + [row for row in loose_products(item) if row not in products]
    except Exception:
        products = []
    products = personalize(products, profile.get("taste"))
    if not products:
        return f"Live listings: {item}\n\nNo clear store listing came back just now."
    avoid = list((profile.get("taste") or {}).get("avoid") or [])
    lines = [f"Live listings: {item}", ""]
    if avoid:
        lines.append(f"Ranked with brands you keep. Avoided: {', '.join(avoid)}.")
    else:
        lines.append("Ranked with brands and colors you keep.")
    lines.append("")
    for index, product in enumerate(products[:4], start=1):
        store = product.get("store") or "Store"
        name = product.get("name") or "Product"
        price = f"${product['price']}" if product.get("price") else "price n/a"
        lines.append(f"{index}. {store}")
        lines.append(f"   {name}")
        lines.append(f"   {price}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _companion_answer(question: str, profile: dict) -> str:
    """Answer with the shopper profile plus optional Tavily web evidence."""
    from backend.app.integrations.openai_client import OpenAIClient
    from backend.app.services.shop.guard import gate, sanitize

    blocked = gate(question)
    if blocked is not None:
        return blocked
    evidence = _web_evidence(question, profile)
    prompt = (
        "You are Unmasked, the shopper's texting companion on iMessage.\n"
        "Use the shopper profile and web evidence. Do not invent orders, returns, prices, or policies.\n"
        "If evidence is missing, say so briefly.\n\n"
        "Format the reply like a clear chat answer:\n"
        "- Start with a short title line\n"
        "- Put a blank line between sections\n"
        "- Use short bullets or numbered items for lists\n"
        "- Keep lines short and scannable\n"
        "- Plain text only (no markdown #, **, or code fences)\n"
        "- Prefer several short blocks over one dense paragraph\n\n"
        'Return JSON only: {"answer": "the reply with real newline characters"}\n\n'
        f"Shopper profile:\n{_profile_block(profile)}\n\n"
        f"Web evidence:\n{evidence or '- none retrieved'}\n\n"
        f"Question: {question}"
    )
    try:
        raw = OpenAIClient().complete(prompt)
    except RuntimeError:
        if evidence:
            return sanitize(_evidence_fallback(evidence))
        return sanitize(
            _pack(_profile_answer(profile), "Ask me to find a product online if you want listings.")
        )
    return sanitize(_answer_json(raw) or _profile_answer(profile))


def _evidence_fallback(evidence: str) -> str:
    lines = ["From the web", ""]
    for row in evidence.splitlines()[:4]:
        cleaned = row.strip().lstrip("- ").strip()
        if cleaned:
            lines.append(f"• {cleaned[:220]}")
    return "\n".join(lines)


def _web_evidence(question: str, profile: dict) -> str:
    if not (_WEB.search(question) or _FIND.search(question) or len(question.split()) >= 4):
        return ""
    try:
        from backend.app.integrations.tavily_client import TavilyClient

        hits = TavilyClient().search(question, max_results=4) or []
    except Exception:
        hits = []
    lines = []
    for hit in hits[:4]:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or "").strip()
        url = str(hit.get("url") or "").strip()
        snippet = str(hit.get("content") or hit.get("snippet") or "").strip().replace("\n", " ")[:220]
        if title or snippet:
            lines.append(f"- {title}: {snippet} {url}".strip())
    kept = profile.get("kept") or []
    if kept and not lines:
        try:
            from backend.app.integrations.tavily_client import TavilyClient

            seed = kept[0]["name"]
            hits = TavilyClient().search(f"{seed} alternatives review", max_results=3) or []
            for hit in hits[:3]:
                if isinstance(hit, dict):
                    lines.append(f"- {hit.get('title')}: {str(hit.get('content') or '')[:180]} {hit.get('url') or ''}")
        except Exception:
            pass
    return "\n".join(lines)


def _profile_block(profile: dict) -> str:
    taste = profile.get("taste") or {}
    kept = profile.get("kept") or []
    returned = profile.get("returned") or []
    kept_lines = [
        f"{item['name']} ({item.get('store') or 'store'}, {item.get('status') or 'saved'}, ${item.get('price') or '?'})"
        for item in kept[:6]
    ]
    returned_lines = [item["name"] for item in returned[:4]]
    return "\n".join(
        [
            f"Name: {profile.get('name') or 'unknown'}",
            f"Email: {profile.get('email') or 'unknown'}",
            f"Phone: {profile.get('phone') or 'unknown'}",
            f"Kept orders: {'; '.join(kept_lines) or 'none'}",
            f"Returned: {'; '.join(returned_lines) or 'none'}",
            f"Brands kept: {', '.join(taste.get('brands') or []) or 'none'}",
            f"Colors kept: {', '.join(taste.get('colors') or []) or 'none'}",
            f"Brands avoided: {', '.join(taste.get('avoid') or []) or 'none'}",
        ]
    )


def _answer_json(raw: str) -> str:
    import json

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        try:
            payload = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            answer = str(payload.get("answer") or "").strip()
            if answer:
                return answer
    return raw.strip()


def _orders(user_id: str) -> list:
    try:
        return list(contact().past_orders(user_id))
    except KeyError:
        return []


def _text(name: str, orders: list, taste: dict) -> str:
    who = f"{name}, " if name else ""
    if not orders:
        return (
            f"{who}you're signed in. After a checkout or a bill is saved, "
            "the next sign-in covers those products and what to look at next."
        ).strip()
    status = "; ".join(
        f"{order.product_name} is {(order.delivery_status or 'saved').lower()}"
        for order in orders[:4]
    )
    advice = _advice(orders, taste)
    return f"{who}your products: {status}. {advice}".strip()


def _advice(orders: list, taste: dict) -> str:
    brands = list(taste.get("brands") or [])
    avoid = list(taste.get("avoid") or [])
    kinds = []
    for order in orders:
        if _returned(order):
            continue
        kind = known_kind(order.product_name)
        if kind and kind not in kinds:
            kinds.append(kind)
    parts = []
    if brands and kinds:
        parts.append(f"Look at more {kinds[0]}s from {brands[0]}, which you kept.")
    elif kinds:
        parts.append(f"Look at more {kinds[0]}s like the ones you kept.")
    elif brands:
        parts.append(f"Look at more from {brands[0]}, which you kept.")
    if avoid:
        parts.append(f"{avoid[0]} was returned, so those stay off the list.")
    if not parts:
        parts.append("Similar products will follow the brands and colors on these purchases.")
    return " ".join(parts)


def _products(orders: list, taste: dict) -> list[dict]:
    brands = [item.lower() for item in taste.get("brands") or []]
    rows = []
    for order in orders:
        if _returned(order):
            continue
        name = order.product_name
        kind = known_kind(name)
        brand = next((item for item in brands if item in name.lower()), "")
        because = f"More {kind}s" if kind else "More like this"
        if brand:
            because += f" from {brand}"
        rows.append({"name": name, "because": because + ", based on what you kept."})
    return rows[:4]


def _returned(order) -> bool:
    materials = (order.materials or "").lower()
    status = (order.delivery_status or "").lower()
    return "returned:yes" in materials or status == "returned"
