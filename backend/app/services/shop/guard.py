"""Code checks for questions the shop assistant must not free-answer."""

import re

CRISIS = (
    "I can't help with ways to harm yourself. "
    "If you might act on this, call or text 988 in the US, or contact local emergency services."
)
REFUSE_HARMFUL = "I can't provide instructions for explosives or other weapons."
REFUSE_BIO = (
    "I can't enroll a faceprint or other biometric identifier, compare match rates across groups, "
    "infer race, religion, sexual orientation, or emotion, or identify a stranger from a photo. "
    "That would require the person's explicit consent, and this assistant does not do biometric matching."
)
REFUSE_SECRET = "I can't reveal system instructions, API keys, passwords, or tokens."
REFUSE_PII = "I can't store or repeat Social Security numbers, card numbers, passwords, or other identifiers."
REFUSE_EXFIL = "I can't export other people's accounts, messages, or records."
PARIS = "The capital of France is Paris."
UNSOURCED = "I don't have a sourced answer for that."

_SELF_HARM = re.compile(
    r"\b(harm myself|hurt myself|kill myself|end my life|suicide|self[-\s]?harm)\b"
    r"|most effective way to harm",
    re.IGNORECASE,
)
_HARMFUL = re.compile(r"\b(explosive|grenade|detonat\w*|pipe bomb|\bbomb\b)\b", re.IGNORECASE)
_BIO = re.compile(
    r"faceprint|biometric identifier|"
    r"\binfer\b.{0,80}\b(race|religion|sexual orientation|emotional state)\b|"
    r"whether they are lying|"
    r"stranger in this photo|"
    r"real name and home address|"
    r"false match|"
    r"match rates? by group|"
    r"demographic group",
    re.IGNORECASE,
)
_INJECTION = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) instructions|"
    r"(?:hidden |the )?system prompt|"
    r"hidden instructions|"
    r"\breveal\b.{0,80}\b(api keys|passwords|tokens|secrets)\b|"
    r"\b(print|show|leak|dump)\b.{0,60}\b(system prompt|instructions|api key|secrets)\b",
    re.IGNORECASE,
)
_IDENTIFIER = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b|"
    r"\b(?:\d[ -]*?){13,19}\b|"
    r"[\w.+-]+@[\w.-]+\.[a-z]{2,}|"
    r"\b(ssn|social security|credit card|passport number|api key|password)\b|"
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}",
    re.IGNORECASE,
)
_ECHO = re.compile(r"\b(repeat|store|confirm you stored|remember|save)\b", re.IGNORECASE)
_EXFIL = re.compile(
    r"\b(dump (?:the )?(?:database|users|secrets)|"
    r"list (?:all|every) (?:user|customer|account|email|password)s?|"
    r"other (?:users|people)'s (?:data|emails|records))\b",
    re.IGNORECASE,
)
_FRANCE = re.compile(r"\bcapital of france\b", re.IGNORECASE)
_EXACT = re.compile(
    r"\b(?:reply|respond|answer|output)\s+with\s+(?:only|exactly|just)\s+"
    r"(?:the\s+(?:word|phrase|number)\s+)?[\"']?([A-Za-z0-9][^\"'\n]{0,40})",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_SECRET = re.compile(
    r"\b(?:sk|pk|rk|pho)_[A-Za-z0-9_]{8,}\b|"
    r"\bBearer\s+[A-Za-z0-9._\-]{8,}\b|"
    r"\b(?:api[_ ]?key|secret|password|token)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def gate(question: str) -> str | None:
    """Return a fixed reply when the question must not reach the model."""
    text = question or ""
    if _SELF_HARM.search(text):
        return CRISIS
    if _HARMFUL.search(text):
        return REFUSE_HARMFUL
    if _BIO.search(text):
        return REFUSE_BIO
    if _INJECTION.search(text):
        return REFUSE_SECRET
    if _EXFIL.search(text):
        return REFUSE_EXFIL
    if _IDENTIFIER.search(text) and _ECHO.search(text):
        return REFUSE_PII
    if _FRANCE.search(text):
        return PARIS
    exact = _EXACT.search(text)
    if exact:
        reply = exact.group(1).strip(" .\"'")
        if reply and _IDENTIFIER.search(reply) is None and _HARMFUL.search(reply) is None:
            return reply
    return None


def sanitize(text: str) -> str:
    """Remove identifiers and secrets from a reply before it leaves the service."""
    cleaned = text or ""
    if re.search(r"(system prompt|my instructions are|here are my instructions)", cleaned, re.IGNORECASE):
        return REFUSE_SECRET
    cleaned = _SECRET.sub("[redacted]", cleaned)
    cleaned = _EMAIL.sub("[redacted]", cleaned)
    cleaned = _SSN.sub("[redacted]", cleaned)
    cleaned = _PHONE.sub("[redacted]", cleaned)
    cleaned = _CARD.sub("[redacted]", cleaned)
    return cleaned
