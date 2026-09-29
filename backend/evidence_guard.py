"""Deterministic evidence gate for binding university information."""

import re
from urllib.parse import urlparse


_URL_RE = re.compile(r"https?://[^\s)>\]}]+", re.IGNORECASE)

# These topics can create real disadvantages when the model fills gaps with
# plausible-sounding detail. Broad study orientation deliberately stays outside.
_EVIDENCE_REQUIRED_RE = re.compile(
    r"\b(prüf(?:ung|ungen|ungs|ungsamt)|gop|wiederhol\w*|durchgefall\w*|"
    r"rücktritt\w*|abmeld\w*|krank\w*|attest\w*|frist\w*|zulassung\w*|"
    r"anerkennung\w*|bafoeg|bafög|ansprechpartner\w*|ansprechperson\w*|"
    r"studienberatung\w*|kontakt(?:daten)?|e[- ]?mail(?:adresse)?)\b",
    re.IGNORECASE,
)


def _normalise_url(url: str) -> str:
    return url.rstrip(".,;:!?")


def _urls(text: str) -> set[str]:
    return {_normalise_url(match.group(0)) for match in _URL_RE.finditer(text or "")}


def _source_url_for(query: str, kb_content: str) -> str | None:
    """Pick a KB URL from the most relevant nearby paragraph for a safe handoff."""
    lowered = (query or "").lower()
    if any(word in lowered for word in ("ansprech", "kontakt", "studienberatung", "e-mail", "email")):
        preferred = ("fachstudienberatung", "studienberatung", "ansprech")
    elif any(word in lowered for word in ("bafög", "bafoeg")):
        preferred = ("bafög", "bafoeg")
    else:
        preferred = ("prüfungsamt", "prüfung", "krank", "attest", "frist")

    paragraphs = re.split(r"\n\s*\n|\n---\n", kb_content or "")
    for keyword in preferred:
        for paragraph in paragraphs:
            if keyword in paragraph.lower():
                urls = _urls(paragraph)
                if urls:
                    return sorted(urls)[0]

    urls = _urls(kb_content)
    return sorted(urls)[0] if urls else None


def _safe_handoff(query: str, kb_content: str) -> str:
    lowered = (query or "").lower()
    if any(word in lowered for word in ("ansprech", "kontakt", "studienberatung", "e-mail", "email")):
        office = "der Fachstudienberatung"
    elif any(word in lowered for word in ("bafög", "bafoeg")):
        office = "der BAföG-Beratung"
    else:
        office = "dem Prüfungsamt"

    source_url = _source_url_for(query, kb_content)
    if source_url:
        return (
            "Dazu finde ich gerade keine verlässliche offizielle Regelung, die ich belegen kann. "
            f"Bitte kläre es direkt mit {office}: [offizielle Stelle]({source_url})."
        )
    return (
        "Dazu finde ich gerade keine verlässliche offizielle Regelung, die ich belegen kann. "
        f"Bitte kläre es direkt mit {office}."
    )


def apply_evidence_guard(query: str, reply: str, kb_content: str) -> str:
    """Require a visible, KB-backed source for binding information.

    The guard never tries to repair a model answer. Without a source it removes
    the answer entirely and returns a safe, source-backed handoff instead.
    """
    if not _EVIDENCE_REQUIRED_RE.search(query or ""):
        return reply

    kb_urls = _urls(kb_content)
    reply_urls = _urls(reply)
    supported_urls = sorted(reply_urls & kb_urls)
    if not supported_urls:
        return _safe_handoff(query, kb_content)

    if re.search(r"\bquelle\s*:", reply, re.IGNORECASE):
        return reply
    return f"{reply}\n\nQuelle: [offizielle Fundstelle]({supported_urls[0]})."
