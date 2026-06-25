"""Message generator agent — personalized first-contact WhatsApp message."""

from __future__ import annotations

from loguru import logger

from app.agents.audit_agent import AuditResult
from app.config import settings
from app.llm.client import llm
from app.llm.prompts import (
    EMAIL_SYSTEM,
    EMAIL_USER_TEMPLATE,
    MESSAGE_SYSTEM,
    MESSAGE_USER_TEMPLATE,
)
from app.models import Business


def generate_message(business: Business, audit: AuditResult) -> str:
    """Produce a short, personalized WhatsApp outreach message."""
    problems = ", ".join(audit.problems) or "limited online presence"
    opportunities = (
        ", ".join(audit.opportunities or audit.recommended_services)
        or "website & automation"
    )
    growth = ", ".join(audit.growth_ideas) or "more leads and less manual work"

    user = MESSAGE_USER_TEMPLATE.format(
        name=business.name,
        category=business.category or "business",
        city=business.city or "your city",
        country=business.country or "",
        problems=problems,
        opportunities=opportunities,
        growth_ideas=growth,
        agency_services=settings.agency_services,
        sender_name=settings.agency_sender_name or "the team",
        founder_note=settings.agency_founder_note or "",
        agency_name=settings.agency_name,
        agency_website=settings.agency_website,
        calendar_url=settings.agency_calendar_url or "(none)",
    )

    try:
        msg = llm.chat(MESSAGE_SYSTEM, user, temperature=0.6, max_tokens=220)
        if msg:
            return _ensure_calendar(msg.strip())
    except Exception as exc:
        logger.error("Message LLM call failed for {}: {}", business.name, exc)

    # Fallback template so the pipeline always yields a draft.
    sign = settings.agency_sender_name or settings.agency_name
    return _ensure_calendar(
        f"Hi, I came across {business.name} and noticed {problems}. "
        f"We help {business.category or 'businesses'} with {services}. "
        f"Would you be open to a free audit?\n\n"
        f"{sign} — {settings.agency_name}\n{settings.agency_website}"
    )


def _ensure_calendar(msg: str) -> str:
    """Guarantee the booking link is in the message (don't rely on the LLM)."""
    url = settings.agency_calendar_url
    if not url or url in msg:
        return msg
    return f"{msg}\n\n📅 Book a quick call: {url}"


def generate_email(business: Business, audit: AuditResult) -> tuple[str, str]:
    """Produce (subject, body) for a cold outreach email."""
    problems = ", ".join(audit.problems) or "limited online presence"
    opportunities = (
        ", ".join(audit.opportunities or audit.recommended_services)
        or "website & automation"
    )
    growth = ", ".join(audit.growth_ideas) or "more leads and less manual work"
    user = EMAIL_USER_TEMPLATE.format(
        name=business.name,
        category=business.category or "business",
        city=business.city or "your city",
        country=business.country or "",
        problems=problems,
        opportunities=opportunities,
        growth_ideas=growth,
        sender_name=settings.agency_sender_name or "the team",
        founder_note=settings.agency_founder_note or "",
        agency_name=settings.agency_name,
        agency_website=settings.agency_website,
        calendar_url=settings.agency_calendar_url or "(none)",
        agency_services=settings.agency_services,
    )
    subject = f"Quick idea for {business.name}"
    body = ""
    try:
        data = llm.chat_json(EMAIL_SYSTEM, user, temperature=0.5, max_tokens=400)
        subject = (data.get("subject") or subject).strip()
        body = (data.get("body") or "").strip()
    except Exception as exc:
        logger.error("Email LLM call failed for {}: {}", business.name, exc)

    if not body:
        sign = settings.agency_sender_name or settings.agency_name
        body = (
            f"Hi {business.name} team,\n\n"
            f"I came across your business and noticed {problems}. "
            f"At {settings.agency_name} we help with {services}.\n\n"
            f"Would you be open to a free audit?\n\n"
            f"Best,\n{sign}\n{settings.agency_founder_note}\n{settings.agency_website}"
        )
    # Always include the booking link.
    if settings.agency_calendar_url and settings.agency_calendar_url not in body:
        body += f"\n\nBook a quick call: {settings.agency_calendar_url}"
    return subject, body
