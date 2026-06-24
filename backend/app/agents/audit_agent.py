"""AI audit agent — turns technical signals into commercial opportunities via LLM."""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from app.agents.website_analyzer import WebsiteSignals
from app.llm.client import llm
from app.llm.prompts import AUDIT_SYSTEM, AUDIT_USER_TEMPLATE
from app.models import Business


@dataclass
class AuditResult:
    ai_opportunity_score: int | None = None
    problems: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    recommended_services: list[str] = field(default_factory=list)
    audit_summary: str = ""


def run_audit(business: Business, signals: WebsiteSignals) -> AuditResult:
    """Ask the LLM to analyze the business and return structured opportunities."""
    user = AUDIT_USER_TEMPLATE.format(
        name=business.name,
        category=business.category or "unknown",
        city=business.city or "unknown",
        country=business.country or "unknown",
        website=business.website or "none",
        rating=business.rating if business.rating is not None else "n/a",
        reviews=business.reviews if business.reviews is not None else "n/a",
        has_website=signals.has_website,
        has_ssl=signals.has_ssl,
        mobile_friendly=signals.mobile_friendly,
        has_chatbot=signals.has_chatbot,
        has_whatsapp=signals.has_whatsapp,
        has_lead_form=signals.has_lead_form,
        has_booking=signals.has_booking,
        has_analytics=signals.has_analytics,
        seo_score=signals.seo_score if signals.seo_score is not None else "null",
        page_excerpt=signals.page_excerpt or "(no website text available)",
    )

    from app.config import settings

    system = AUDIT_SYSTEM.format(agency_services=settings.agency_services)
    try:
        data = llm.chat_json(system, user, temperature=0.2, max_tokens=900)
    except Exception as exc:
        logger.error("Audit LLM call failed for {}: {}", business.name, exc)
        return _fallback_audit(signals)

    if not data:
        return _fallback_audit(signals)

    return AuditResult(
        ai_opportunity_score=_as_int(data.get("ai_opportunity_score")),
        problems=_as_list(data.get("problems")),
        opportunities=_as_list(data.get("opportunities")),
        recommended_services=_as_list(data.get("recommended_services")),
        audit_summary=str(data.get("audit_summary", "")).strip(),
    )


def _fallback_audit(signals: WebsiteSignals) -> AuditResult:
    """Deterministic audit if the LLM is unavailable, so the pipeline never blocks."""
    problems, services = [], []
    if not signals.has_website:
        problems.append("No website found")
        services.append("Website Development")
    else:
        if not signals.has_whatsapp:
            problems.append("No WhatsApp integration")
            services.append("WhatsApp Automation")
        if not signals.has_chatbot:
            problems.append("No chatbot / automated support")
            services.append("AI Chatbot")
        if (signals.seo_score or 0) < 50:
            problems.append("Weak on-page SEO")
            services.append("SEO Service")
        if not signals.has_booking:
            problems.append("No online booking")
            services.append("Appointment Booking Agent")
    return AuditResult(
        problems=problems,
        recommended_services=services,
        audit_summary="Heuristic audit (LLM unavailable).",
    )


def _as_int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _as_list(v) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []
