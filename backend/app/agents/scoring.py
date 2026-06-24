"""Rule-based lead scoring.

Deterministic and reliable (preferred over LLM scoring). Higher score = bigger
gap in the business's web presence = better opportunity for the agency.
"""

from __future__ import annotations

from app.agents.website_analyzer import WebsiteSignals
from app.models import Business

# Points added when a capability is MISSING.
WEIGHTS = {
    "no_website": 30,
    "no_whatsapp": 20,
    "no_chatbot": 20,
    "poor_seo": 15,        # seo_score < 50
    "low_reviews": 10,     # reviews < 20
    "no_booking": 15,
    "no_ssl": 10,
}


def score_lead(business: Business, signals: WebsiteSignals) -> int:
    """Return a 0-100 lead score from technical signals + business metadata."""
    score = 0

    if not signals.has_website:
        # No website at all is the strongest signal — cap there and return.
        score += WEIGHTS["no_website"]
        if (business.reviews or 0) < 20:
            score += WEIGHTS["low_reviews"]
        return min(score, 100)

    if not signals.has_whatsapp:
        score += WEIGHTS["no_whatsapp"]
    if not signals.has_chatbot:
        score += WEIGHTS["no_chatbot"]
    if (signals.seo_score or 0) < 50:
        score += WEIGHTS["poor_seo"]
    if (business.reviews or 0) < 20:
        score += WEIGHTS["low_reviews"]
    if not signals.has_booking:
        score += WEIGHTS["no_booking"]
    if not signals.has_ssl:
        score += WEIGHTS["no_ssl"]

    return min(score, 100)


def score_band(score: int | None) -> str:
    """Map a numeric score to a qualitative band."""
    if score is None:
        return "unknown"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"
