"""Email sender with Gmail primary + automatic Brevo failover.

Sends via Gmail SMTP. If Gmail rejects with a quota/rate/limit error (e.g. the
daily sending cap is reached), it automatically retries via Brevo so outreach
keeps flowing. The "From" address stays the same (must be a verified sender in
Brevo). Dry-run (EMAIL_DRY_RUN=true) simulates without sending.
"""

from __future__ import annotations

import html as html_lib
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from loguru import logger

from app.config import settings

# Substrings that indicate "Gmail is rate/quota limited" -> worth failing over.
_LIMIT_HINTS = (
    "limit", "quota", "exceeded", "too many", "rate", "5.4.5", "4.7.0", "550", "452",
)


@dataclass
class EmailResult:
    to: str
    ok: bool
    dry_run: bool = False
    provider: str | None = None
    error: str | None = None


def build_html_email(body: str) -> str:
    """Wrap a plain-text pitch into a clean, branded HTML email."""
    cal = settings.agency_calendar_url
    agency = settings.agency_name
    website = settings.agency_website
    sender = settings.agency_sender_name
    note = settings.agency_founder_note

    # Drop any raw booking-link line from the text — we show it as a button instead.
    lines = []
    for ln in body.splitlines():
        if cal and cal in ln:
            continue
        lines.append(ln)
    clean = "\n".join(lines).strip()

    # Build paragraphs from blank-line-separated blocks.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", clean) if b.strip()]
    paragraphs = "".join(
        f'<p style="margin:0 0 14px;line-height:1.6;color:#334155;font-size:15px;">'
        f'{html_lib.escape(b).replace(chr(10), "<br>")}</p>'
        for b in blocks
    )

    cta = (
        f'<tr><td style="padding:6px 0 22px;">'
        f'<a href="{html_lib.escape(cal)}" '
        f'style="background:#4f46e5;color:#ffffff;text-decoration:none;'
        f'padding:12px 22px;border-radius:8px;font-weight:600;font-size:15px;'
        f'display:inline-block;">📅 Book a Free Call</a></td></tr>'
        if cal
        else ""
    )

    return f"""\
<!DOCTYPE html><html><body style="margin:0;background:#f5f7fb;padding:24px;
font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
style="max-width:600px;background:#ffffff;border-radius:14px;overflow:hidden;
box-shadow:0 8px 24px -16px rgba(16,24,40,.25);">
  <tr><td style="background:#4f46e5;padding:20px 28px;">
    <span style="color:#fff;font-size:20px;font-weight:700;">{html_lib.escape(agency)}</span>
    <span style="color:#c7d2fe;font-size:13px;"> &nbsp; AI · Web · Automation</span>
  </td></tr>
  <tr><td style="padding:28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td>{paragraphs}</td></tr>
      {cta}
    </table>
    <hr style="border:none;border-top:1px solid #e6e9f0;margin:8px 0 16px;">
    <p style="margin:0;color:#64748b;font-size:13px;line-height:1.5;">
      {html_lib.escape(sender)}<br>
      {html_lib.escape(note)}<br>
      <a href="{html_lib.escape(website)}" style="color:#4f46e5;text-decoration:none;">{html_lib.escape(website)}</a>
    </p>
  </td></tr>
</table>
<p style="color:#94a3b8;font-size:11px;margin:14px 0 0;">
  You received this because your business is publicly listed. Reply STOP to opt out.
</p>
</td></tr></table></body></html>"""


def _build(from_addr: str, to_addr: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    # Plain text only — reads like a real person wrote it (better replies + less spam).
    msg.set_content(body)
    return msg


def _smtp_send(host: str, port: int, login: str, password: str, msg: EmailMessage) -> None:
    """Low-level send. Port 465 -> SSL, otherwise STARTTLS."""
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(login, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
            s.login(login, password)
            s.send_message(msg)


def _is_limit_error(err: str) -> bool:
    e = err.lower()
    return any(h in e for h in _LIMIT_HINTS)


def _send_brevo_api(to_addr: str, subject: str, body: str) -> EmailResult:
    """Send via Brevo's HTTP API (port 443) — works on clouds that block SMTP."""
    import httpx

    try:
        resp = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": settings.brevo_api_key,
                "content-type": "application/json",
                "accept": "application/json",
            },
            json={
                "sender": {
                    "name": settings.agency_sender_name or settings.agency_name,
                    "email": settings.email_sender,
                },
                "to": [{"email": to_addr}],
                "subject": subject,
                "textContent": body,
            },
            timeout=30,
        )
        if resp.status_code in (200, 201):
            logger.info("Emailed {} via Brevo API", to_addr)
            return EmailResult(to=to_addr, ok=True, provider="brevo-api")
        return EmailResult(
            to=to_addr, ok=False, provider="brevo-api",
            error=f"{resp.status_code}: {resp.text[:160]}",
        )
    except Exception as exc:
        return EmailResult(to=to_addr, ok=False, provider="brevo-api", error=str(exc))


def send_email(to_addr: str, subject: str, body: str) -> EmailResult:
    """Send an email via the configured provider (Gmail SMTP or Brevo HTTP API)."""
    if not to_addr or "@" not in to_addr:
        return EmailResult(to=to_addr, ok=False, error="invalid email")

    if settings.email_dry_run:
        logger.info("[EMAIL DRY-RUN] would email {} | subj: {}", to_addr, subject[:50])
        return EmailResult(to=to_addr, ok=True, dry_run=True, provider="dry-run")

    # Brevo HTTP API (preferred on clouds that block SMTP).
    if settings.email_provider == "brevo" and settings.brevo_api_key:
        return _send_brevo_api(to_addr, subject, body)

    from_addr = settings.email_sender
    msg = _build(from_addr, to_addr, subject, body)

    gmail_ready = bool(settings.email_sender and settings.email_app_password)
    brevo_ready = bool(settings.brevo_login and settings.brevo_smtp_key)

    # 1) Try Gmail.
    gmail_err: str | None = None
    if gmail_ready:
        try:
            _smtp_send(
                settings.smtp_host, settings.smtp_port,
                settings.email_sender, settings.email_app_password, msg,
            )
            logger.info("Emailed {} via Gmail", to_addr)
            return EmailResult(to=to_addr, ok=True, provider="gmail")
        except Exception as exc:
            gmail_err = str(exc)
            logger.warning("Gmail send to {} failed: {}", to_addr, gmail_err[:120])

    # 1b) Brevo HTTP API failover (works even when SMTP is blocked, e.g. Render).
    if settings.brevo_api_key:
        res = _send_brevo_api(to_addr, subject, body)
        if res.ok:
            return res

    # 2) Failover to Brevo SMTP on a limit error (or if Gmail isn't configured).
    should_failover = brevo_ready and settings.email_failover and (
        not gmail_ready or (gmail_err and _is_limit_error(gmail_err))
    )
    if should_failover:
        try:
            _smtp_send(
                settings.brevo_smtp_host, settings.brevo_smtp_port,
                settings.brevo_login, settings.brevo_smtp_key, msg,
            )
            logger.info("Emailed {} via Brevo (failover)", to_addr)
            return EmailResult(to=to_addr, ok=True, provider="brevo")
        except Exception as exc:
            return EmailResult(
                to=to_addr, ok=False, provider="brevo", error=str(exc)
            )

    if not gmail_ready and not brevo_ready:
        return EmailResult(to=to_addr, ok=False, error="no email provider configured")
    return EmailResult(to=to_addr, ok=False, provider="gmail", error=gmail_err or "send failed")
