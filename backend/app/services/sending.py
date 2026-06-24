"""Service layer for outbound WhatsApp sending + status persistence.

Dry-run mode (WHATSAPP_DRY_RUN=true) NEVER launches a browser — it just simulates
the send and marks the message, so you can test the whole flow safely and instantly.
Real sending opens one WhatsApp Web session, requires an existing login (use the
"Connect WhatsApp" QR first), and throttles between messages.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Business,
    Contacted,
    LeadStatus,
    Message,
    MessageChannel,
    MessageStatus,
)
from app.senders.email_sender import send_email
from app.senders.whatsapp_web import WhatsAppWebSender, normalize_phone

# Lead states that mean "already reached out" — never message these again.
_ALREADY_CONTACTED = (
    LeadStatus.CONTACTED,
    LeadStatus.REPLIED,
    LeadStatus.MEETING,
    LeadStatus.WON,
    LeadStatus.LOST,
)

ProgressCb = Callable[[int, int, int], None]  # (done, total, sent)


def _mark(db: Session, msg: Message, status: MessageStatus) -> None:
    msg.status = status
    if status == MessageStatus.SENT:
        msg.sent_at = datetime.utcnow()
    db.commit()


def _archive_and_delete(db: Session, biz: Business, channel: str) -> None:
    """Log the contact in the lean `contacted` table, then delete the heavy lead
    data (business + its audits + messages) so the DB stays small and the lead is
    never scraped or contacted again."""
    db.add(
        Contacted(
            name=biz.name,
            city=biz.city,
            phone=biz.phone,
            whatsapp_number=biz.whatsapp_number,
            email=biz.email,
            channel=channel,
        )
    )
    db.delete(biz)  # cascade removes website_audits + messages
    db.commit()


def _target_number(biz: Business) -> str | None:
    """The number we'll actually message: confirmed WhatsApp number if known."""
    return biz.whatsapp_number or normalize_phone(biz.phone, biz.dial_code)


def _result(msg: Message, biz: Business, ok: bool, dry: bool, err: str | None) -> dict:
    return {
        "message_id": msg.id,
        "business": biz.name,
        "phone": _target_number(biz),
        "ok": ok,
        "dry_run": dry,
        "error": err,
    }


def _select_drafts(db: Session, limit: int, min_score: int, only_whatsapp: bool = True):
    stmt = (
        select(Message, Business)
        .join(Business, Business.id == Message.business_id)
        .where(Message.status == MessageStatus.DRAFT)
        .where(Business.lead_score >= min_score)
        .where(Business.status.notin_(_ALREADY_CONTACTED))  # never re-message
    )
    if only_whatsapp:
        # Only businesses with a WhatsApp-reachable number.
        stmt = stmt.where(Business.whatsapp_number.is_not(None))
    else:
        stmt = stmt.where(Business.phone.is_not(None))
    stmt = stmt.order_by(Business.lead_score.desc().nullslast()).limit(limit)
    return list(db.execute(stmt).all())


def send_single_message(db: Session, message_id: int) -> dict:
    """Send one drafted message by id. Dry-run simulates without a browser."""
    msg = db.get(Message, message_id)
    if not msg:
        return {"message_id": message_id, "ok": False, "error": "message not found"}
    biz = db.get(Business, msg.business_id)
    target = _target_number(biz) if biz else None
    if not biz or not target:
        _mark(db, msg, MessageStatus.FAILED)
        return {"message_id": message_id, "ok": False, "error": "no WhatsApp number"}

    if settings.whatsapp_dry_run:
        logger.info("[DRY-RUN] simulate send to {}", biz.name)
        _mark(db, msg, MessageStatus.SENT)
        biz.status = LeadStatus.CONTACTED
        db.commit()
        return _result(msg, biz, ok=True, dry=True, err=None)

    with WhatsAppWebSender() as wa:
        if not wa.ensure_logged_in(qr_wait_seconds=0):
            return {"message_id": message_id, "ok": False, "error": "not logged in (scan QR first)"}
        res = wa.send(target, msg.body, dial_code=biz.dial_code)

    out = _result(msg, biz, ok=res.ok, dry=res.dry_run, err=res.error)
    if res.ok and not res.dry_run:
        _archive_and_delete(db, biz, "whatsapp")
    elif res.ok:
        _mark(db, msg, MessageStatus.SENT)  # dry-run: keep, just mark
    else:
        _mark(db, msg, MessageStatus.FAILED)
    return out


def send_batch(
    db: Session,
    limit: int | None = None,
    min_score: int = 0,
    on_progress: ProgressCb | None = None,
    only_whatsapp: bool = True,
) -> list[dict]:
    """Send DRAFT messages to WhatsApp-ready leads (best first), within the cap.

    only_whatsapp=True (default) sends only to businesses with a confirmed
    WhatsApp number. Dry-run simulates instantly; real opens one login session.
    """
    cap = min(limit or settings.whatsapp_daily_limit, settings.whatsapp_daily_limit)
    rows = _select_drafts(db, cap, min_score, only_whatsapp=only_whatsapp)
    total = len(rows)
    out: list[dict] = []
    sent = 0
    if total == 0:
        return out

    # ---- Dry-run: no browser ----
    if settings.whatsapp_dry_run:
        for i, (msg, biz) in enumerate(rows):
            _mark(db, msg, MessageStatus.SENT)
            biz.status = LeadStatus.CONTACTED
            db.commit()
            sent += 1
            out.append(_result(msg, biz, ok=True, dry=True, err=None))
            if on_progress:
                on_progress(i + 1, total, sent)
        logger.info("[DRY-RUN] simulated {} messages.", total)
        return out

    # ---- Real send: one session ----
    with WhatsAppWebSender() as wa:
        if not wa.ensure_logged_in(qr_wait_seconds=0):
            return [{"ok": False, "error": "not logged in (scan the QR via Connect first)"}]
        for i, (msg, biz) in enumerate(rows):
            res = wa.send(_target_number(biz), msg.body, dial_code=biz.dial_code)
            out.append(_result(msg, biz, ok=res.ok, dry=res.dry_run, err=res.error))
            if res.ok:
                _archive_and_delete(db, biz, "whatsapp")  # log + delete heavy data
                sent += 1
            else:
                _mark(db, msg, MessageStatus.FAILED)
            if on_progress:
                on_progress(i + 1, total, sent)
            logger.info("Send {}/{}: {} -> ok={}", i + 1, total, biz.name, res.ok)
            if i < total - 1:
                wa.throttle()
    return out


def _select_email_drafts(db: Session, limit: int, min_score: int):
    """DRAFT email messages for not-yet-contacted businesses that have an email."""
    stmt = (
        select(Message, Business)
        .join(Business, Business.id == Message.business_id)
        .where(Message.status == MessageStatus.DRAFT)
        .where(Message.channel == MessageChannel.EMAIL)
        .where(Business.email.is_not(None))
        .where(Business.lead_score >= min_score)
        .where(Business.status.notin_(_ALREADY_CONTACTED))
        .order_by(Business.lead_score.desc().nullslast())
        .limit(limit)
    )
    return list(db.execute(stmt).all())


def send_email_batch(
    db: Session,
    limit: int | None = None,
    min_score: int = 0,
    on_progress: ProgressCb | None = None,
) -> list[dict]:
    """Email all DRAFT email-leads (businesses with an email, no WhatsApp)."""
    cap = min(limit or settings.email_daily_limit, settings.email_daily_limit)
    rows = _select_email_drafts(db, cap, min_score)
    total = len(rows)
    out: list[dict] = []
    sent = 0
    for i, (msg, biz) in enumerate(rows):
        res = send_email(biz.email, msg.subject or f"Quick idea for {biz.name}", msg.body)
        out.append(
            {
                "message_id": msg.id,
                "business": biz.name,
                "email": biz.email,
                "ok": res.ok,
                "dry_run": res.dry_run,
                "error": res.error,
            }
        )
        if res.ok and not res.dry_run:
            _archive_and_delete(db, biz, "email")  # log + delete heavy data
            sent += 1
        elif res.ok:
            _mark(db, msg, MessageStatus.SENT)  # dry-run
        else:
            _mark(db, msg, MessageStatus.FAILED)
        if on_progress:
            on_progress(i + 1, total, sent)
        logger.info("Email {}/{}: {} -> ok={}", i + 1, total, biz.name, res.ok)
    return out
