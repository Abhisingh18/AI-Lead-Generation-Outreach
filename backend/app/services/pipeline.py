"""Pipeline orchestration: scrape -> persist -> analyze -> audit -> score -> message.

This is the Phase-1 sequential pipeline. In Phase 2 the same steps become
independent LangGraph nodes (LeadCollector -> WebsiteAudit -> Opportunity ->
Scoring -> Message -> CRM); the functions here are written to port cleanly.
"""

from __future__ import annotations

import json

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.audit_agent import run_audit
from app.agents.message_generator import generate_email, generate_message
from app.agents.scoring import score_lead
from app.agents.website_analyzer import analyze_website
from app.models import (
    Business,
    Contacted,
    LeadStatus,
    Message,
    MessageChannel,
    MessageStatus,
    WebsiteAudit,
)
from app.scrapers.google_maps import ScrapedBusiness


def upsert_business(db: Session, sb: ScrapedBusiness) -> Business | None:
    """Insert/update a business by (name, city). Returns None if already contacted
    (suppressed) so we never re-scrape or re-message a lead we've reached out to."""
    already = db.scalar(
        select(Contacted).where(Contacted.name == sb.name, Contacted.city == sb.city)
    )
    if already:
        logger.debug("Skipping already-contacted lead: {} ({})", sb.name, sb.city)
        return None

    existing = db.scalar(
        select(Business).where(Business.name == sb.name, Business.city == sb.city)
    )
    if existing:
        # Refresh contact fields if we learned something new.
        existing.phone = existing.phone or sb.phone
        existing.website = existing.website or sb.website
        existing.address = existing.address or sb.address
        existing.rating = sb.rating if sb.rating is not None else existing.rating
        existing.reviews = sb.reviews if sb.reviews is not None else existing.reviews
        db.flush()
        return existing

    biz = Business(
        name=sb.name,
        category=sb.category,
        phone=sb.phone,
        website=sb.website,
        address=sb.address,
        city=sb.city,
        country=sb.country,
        dial_code=sb.dial_code,
        rating=sb.rating,
        reviews=sb.reviews,
        source=sb.source,
        status=LeadStatus.NEW,
    )
    db.add(biz)
    db.flush()
    return biz


def process_business(db: Session, business: Business) -> dict:
    """Run analyze -> audit -> score -> message for one business and persist it."""
    result = {
        "business_id": business.id,
        "name": business.name,
        "lead_score": None,
        "audit_id": None,
        "message_id": None,
        "error": None,
    }
    try:
        # Skip leads we've already contacted, so re-scraping never re-messages them.
        if business.status in (
            LeadStatus.CONTACTED,
            LeadStatus.REPLIED,
            LeadStatus.MEETING,
            LeadStatus.WON,
            LeadStatus.LOST,
        ):
            result["error"] = "already contacted (skipped)"
            existing = db.scalar(
                select(Message)
                .where(Message.business_id == business.id)
                .order_by(Message.id.desc())
            )
            result["message_id"] = existing.id if existing else None
            return result

        # 1) Technical website analysis
        signals = analyze_website(business.website)

        # 1b) Determine a WhatsApp-reachable number (site wa.me > mobile heuristic)
        from app.senders.whatsapp_web import whatsapp_ready_number

        business.whatsapp_number = whatsapp_ready_number(
            signals.whatsapp_number, business.phone, business.dial_code
        )
        # Capture a contact email from the website if we don't have one yet.
        if not business.email and signals.email:
            business.email = signals.email

        # 2) AI audit
        audit = run_audit(business, signals)

        # 3) Rule-based lead score
        lead_score = score_lead(business, signals)
        business.lead_score = lead_score
        result["lead_score"] = lead_score

        # 4) Persist audit row
        audit_row = WebsiteAudit(
            business_id=business.id,
            has_website=signals.has_website,
            has_ssl=signals.has_ssl,
            mobile_friendly=signals.mobile_friendly,
            has_chatbot=signals.has_chatbot,
            has_whatsapp=signals.has_whatsapp,
            has_lead_form=signals.has_lead_form,
            has_booking=signals.has_booking,
            has_analytics=signals.has_analytics,
            seo_score=signals.seo_score,
            ai_opportunity_score=audit.ai_opportunity_score,
            problems=json.dumps(audit.problems, ensure_ascii=False),
            opportunities=json.dumps(audit.opportunities, ensure_ascii=False),
            recommended_services=json.dumps(audit.recommended_services, ensure_ascii=False),
            audit_summary=audit.audit_summary,
        )
        db.add(audit_row)
        db.flush()
        result["audit_id"] = audit_row.id
        business.status = LeadStatus.SCORED

        # 5) Generate the outreach draft, routed by available channel:
        #    has WhatsApp -> WhatsApp message; else has email -> email; else WhatsApp.
        if business.whatsapp_number:
            channel = MessageChannel.WHATSAPP
            subject = None
            body = generate_message(business, audit)
        elif business.email:
            channel = MessageChannel.EMAIL
            subject, body = generate_email(business, audit)
        else:
            channel = MessageChannel.WHATSAPP
            subject = None
            body = generate_message(business, audit)

        # Reuse an existing draft instead of duplicating.
        msg = db.scalar(
            select(Message)
            .where(
                Message.business_id == business.id,
                Message.status == MessageStatus.DRAFT,
            )
            .order_by(Message.id.desc())
        )
        if msg:
            msg.channel = channel
            msg.subject = subject
            msg.body = body
        else:
            msg = Message(
                business_id=business.id,
                channel=channel,
                subject=subject,
                body=body,
                status=MessageStatus.DRAFT,
            )
            db.add(msg)
        db.flush()
        result["message_id"] = msg.id
        business.status = LeadStatus.MESSAGE_READY

        db.commit()
        logger.info("Processed '{}' -> score={}", business.name, lead_score)
    except Exception as exc:
        db.rollback()
        logger.exception("Pipeline failed for '{}'", business.name)
        result["error"] = str(exc)
    return result


async def scrape_and_process(
    db: Session,
    city: str,
    category: str,
    max_results: int | None,
    run_pipeline: bool,
    country: str | None = None,
    dial_code: str = "91",
) -> list[dict]:
    """Full Phase-1 flow for one city+category search (any country)."""
    # Import here to keep Playwright optional for parts of the app that don't scrape.
    from app.scrapers.google_maps import scrape_google_maps

    scraped = await scrape_google_maps(
        city, category, max_results, country=country, dial_code=dial_code
    )
    out: list[dict] = []
    for sb in scraped:
        biz = upsert_business(db, sb)
        if biz is None:  # already contacted — skip
            continue
        db.commit()
        if run_pipeline:
            out.append(process_business(db, biz))
        else:
            out.append(
                {
                    "business_id": biz.id,
                    "name": biz.name,
                    "lead_score": biz.lead_score,
                    "audit_id": None,
                    "message_id": None,
                    "error": None,
                }
            )
    return out
