"""HTTP API: scraping, leads, audits, messages, and a simple dashboard summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Business,
    Contacted,
    LeadStatus,
    Message,
    MessageStatus,
    WebsiteAudit,
)
from app.schemas import (
    BusinessOut,
    MessageOut,
    PipelineResult,
    ScrapeRequest,
    WebsiteAuditOut,
)
from app.senders.wa_login_manager import login_manager
from app.services.jobs import email_job, scrape_job, send_job
from app.services.pipeline import process_business
from app.services.sending import send_single_message

router = APIRouter(prefix="/api", tags=["leadgen"])


# ----------------------------- Scrape -----------------------------


@router.post("/scrape")
async def scrape(req: ScrapeRequest):
    """Kick off a background scrape+pipeline and return immediately.

    Poll GET /api/scrape/status for progress; leads appear live via /api/dashboard/leads.
    """
    return scrape_job.start(
        req.city,
        req.category,
        req.max_results,
        req.country,
        req.dial_code,
        req.run_pipeline,
    )


@router.get("/scrape/status")
def scrape_status():
    """Progress of the current/last scrape job."""
    return scrape_job.snapshot()


# ----------------------------- Leads -----------------------------


@router.get("/leads", response_model=list[BusinessOut])
def list_leads(
    db: Session = Depends(get_db),
    city: str | None = None,
    category: str | None = None,
    status: LeadStatus | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List leads with filters, newest first."""
    stmt = select(Business)
    if city:
        stmt = stmt.where(Business.city == city)
    if category:
        stmt = stmt.where(Business.category == category)
    if status:
        stmt = stmt.where(Business.status == status)
    if min_score is not None:
        stmt = stmt.where(Business.lead_score >= min_score)
    stmt = stmt.order_by(Business.lead_score.desc().nullslast(), Business.id.desc())
    stmt = stmt.limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.get("/leads/{business_id}", response_model=BusinessOut)
def get_lead(business_id: int, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Lead not found")
    return biz


@router.post("/leads/{business_id}/process", response_model=PipelineResult)
def process_lead(business_id: int, db: Session = Depends(get_db)):
    """Re-run analyze -> audit -> score -> message for a single existing lead."""
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Lead not found")
    return process_business(db, biz)


# ----------------------------- Audits -----------------------------


@router.get("/leads/{business_id}/audits", response_model=list[WebsiteAuditOut])
def lead_audits(business_id: int, db: Session = Depends(get_db)):
    stmt = (
        select(WebsiteAudit)
        .where(WebsiteAudit.business_id == business_id)
        .order_by(WebsiteAudit.id.desc())
    )
    return list(db.scalars(stmt))


# ----------------------------- Messages -----------------------------


@router.get("/leads/{business_id}/messages", response_model=list[MessageOut])
def lead_messages(business_id: int, db: Session = Depends(get_db)):
    stmt = (
        select(Message)
        .where(Message.business_id == business_id)
        .order_by(Message.id.desc())
    )
    return list(db.scalars(stmt))


# ----------------------------- WhatsApp login (QR) -----------------------------


@router.post("/whatsapp/connect")
def whatsapp_connect():
    """Start a background WhatsApp Web session and begin capturing the QR code."""
    return login_manager.start()


@router.get("/whatsapp/status")
def whatsapp_status():
    """Poll login status + current QR image (data URL) for the dashboard."""
    return login_manager.snapshot()


# ----------------------------- Dashboard data -----------------------------


@router.get("/dashboard/leads")
def dashboard_leads(
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
):
    """Leads joined with their latest generated message + audit summary (for the UI)."""
    leads = list(
        db.scalars(
            select(Business)
            .order_by(Business.lead_score.desc().nullslast(), Business.id.desc())
            .limit(limit)
        )
    )
    out = []
    for b in leads:
        latest_msg = db.scalar(
            select(Message)
            .where(Message.business_id == b.id)
            .order_by(Message.id.desc())
            .limit(1)
        )
        latest_audit = db.scalar(
            select(WebsiteAudit)
            .where(WebsiteAudit.business_id == b.id)
            .order_by(WebsiteAudit.id.desc())
            .limit(1)
        )
        out.append(
            {
                "id": b.id,
                "name": b.name,
                "category": b.category,
                "city": b.city,
                "country": b.country,
                "phone": b.phone,
                "whatsapp_number": b.whatsapp_number,
                "email": b.email,
                "website": b.website,
                "rating": b.rating,
                "reviews": b.reviews,
                "lead_score": b.lead_score,
                "status": b.status.value if b.status else None,
                "audit_summary": latest_audit.audit_summary if latest_audit else None,
                "message_id": latest_msg.id if latest_msg else None,
                "message": latest_msg.body if latest_msg else None,
                "message_status": latest_msg.status.value if latest_msg else None,
                "channel": latest_msg.channel.value if latest_msg else None,
                "subject": latest_msg.subject if latest_msg else None,
            }
        )
    return out


# ----------------------------- WhatsApp sending -----------------------------


@router.post("/messages/{message_id}/send")
def send_message(message_id: int, db: Session = Depends(get_db)):
    """Send one drafted WhatsApp message. First call opens WhatsApp Web for QR login."""
    return send_single_message(db, message_id)


@router.post("/send/batch")
def send_messages_batch(
    limit: int | None = Query(None, ge=1, le=200),
    min_score: int = Query(0, ge=0, le=100),
    only_whatsapp: bool = Query(True),
):
    """Start a background send to WhatsApp-ready DRAFT leads (best first, daily cap).

    only_whatsapp=true (default) sends only to businesses with a confirmed WhatsApp
    number. Dry-run (WHATSAPP_DRY_RUN=true) simulates instantly. Poll /api/send/status.
    """
    return send_job.start(limit, min_score, only_whatsapp)


@router.get("/send/status")
def send_status():
    """Progress of the current/last WhatsApp send job."""
    return send_job.snapshot()


@router.post("/send/emails")
def send_emails(
    limit: int | None = Query(None, ge=1, le=200),
    min_score: int = Query(0, ge=0, le=100),
):
    """Start a background email send to email-leads (businesses with no WhatsApp).

    Email dry-run (EMAIL_DRY_RUN=true) simulates. Poll /api/send/emails/status.
    """
    return email_job.start(limit, min_score)


@router.get("/send/emails/status")
def send_emails_status():
    """Progress of the current/last email send job."""
    return email_job.snapshot()


# ----------------------------- Dashboard -----------------------------


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """High-level counters for the dashboard."""
    total = db.scalar(select(func.count(Business.id))) or 0
    qualified = db.scalar(
        select(func.count(Business.id)).where(Business.lead_score >= 70)
    ) or 0
    wa_ready = db.scalar(
        select(func.count(Business.id)).where(Business.whatsapp_number.is_not(None))
    ) or 0
    email_ready = db.scalar(
        select(func.count(Business.id)).where(
            Business.whatsapp_number.is_(None), Business.email.is_not(None)
        )
    ) or 0
    # Real sends are archived in `contacted` (and their messages deleted); dry-run
    # sends stay as SENT messages. Count both so the number reflects all outreach.
    sent_msgs = db.scalar(
        select(func.count(Message.id)).where(Message.status == MessageStatus.SENT)
    ) or 0
    contacted = db.scalar(select(func.count(Contacted.id))) or 0
    sent = sent_msgs + contacted
    drafts = db.scalar(
        select(func.count(Message.id)).where(Message.status == MessageStatus.DRAFT)
    ) or 0
    return {
        "total_leads": total,
        "qualified_leads": qualified,
        "whatsapp_ready": wa_ready,
        "email_ready": email_ready,
        "messages_sent": sent,
        "contacted": contacted,
        "messages_draft": drafts,
    }
