"""WhatsApp sender via Playwright + WhatsApp Web (no API cost, small scale).

How it works:
- A *persistent* Chromium profile is stored in WHATSAPP_SESSION_DIR. You scan the
  QR code ONCE (from your number, e.g. 9648531091) and the login is remembered.
- After that, messages are sent by opening web.whatsapp.com/send?phone=...&text=...
  and clicking the send button.

SAFETY / COMPLIANCE (read me):
- This automates a personal WhatsApp account and can get the number banned if used
  to spam. Keep volumes low, randomize delays, only message public business
  contacts who can reasonably expect outreach, and always honor opt-outs.
- WHATSAPP_DRY_RUN=true (default) simulates sending without actually sending.
- For real scale use the official WhatsApp Business / Meta Cloud API instead.

NOTE: uses the *sync* Playwright API on purpose — call it from FastAPI sync
endpoints (which run in a worker thread), never from inside the asyncio loop.
"""

from __future__ import annotations

import random
import re
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from app.config import settings

WA_BASE = "https://web.whatsapp.com"


@dataclass
class SendResult:
    phone: str
    ok: bool
    dry_run: bool = False
    error: str | None = None


def normalize_phone(raw: str | None, dial_code: str | None = None) -> str | None:
    """Return a digits-only international number (no +) for WhatsApp, or None.

    Works for any country: pass the destination `dial_code` (e.g. 1=US, 44=UK,
    91=India). National-format numbers (with a trunk leading 0) get the dial code
    prepended; numbers already in international format are kept as-is.
    """
    if not raw:
        return None
    cc = (dial_code or settings.whatsapp_country_code).lstrip("+")
    had_plus = raw.strip().startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None

    # Already international (explicit + or already starts with the dial code).
    if had_plus:
        return digits
    if cc and digits.startswith(cc) and len(digits) > len(cc) + 6:
        return digits

    # National format: drop trunk leading zeros, then prepend the dial code.
    digits = digits.lstrip("0")
    return (cc + digits) if cc else digits


def whatsapp_ready_number(
    site_wa: str | None, phone: str | None, dial_code: str | None
) -> str | None:
    """Return a number we can confidently reach on WhatsApp, or None.

    Priority: a WhatsApp number found on the business website (confirmed) > a
    likely mobile number (India heuristic). Landlines return None so we don't
    waste sends on numbers that aren't on WhatsApp.
    """
    # 1) Confirmed from the website's wa.me link.
    if site_wa:
        digits = re.sub(r"\D", "", site_wa)
        if 8 <= len(digits) <= 15:
            return digits

    # 2) Mobile-number heuristic by country (mobiles are almost always on WhatsApp).
    cc = (dial_code or "").lstrip("+")
    if phone:
        nat = re.sub(r"\D", "", phone).lstrip("0")
        # India: 10-digit starting 6-9.
        if cc == "91" and len(nat) == 10 and nat[0] in "6789":
            return "91" + nat
        # UK: 10-digit mobile starting 7 (e.g. 07xxx -> 447xxx).
        if cc == "44" and len(nat) == 10 and nat[0] == "7":
            return "44" + nat
        # UAE: 9-digit mobile starting 5.
        if cc == "971" and len(nat) == 9 and nat[0] == "5":
            return "971" + nat
    return None


class WhatsAppWebSender:
    """Reusable sender backed by a persistent Playwright context."""

    def __init__(self, headless: bool | None = None) -> None:
        self._pw = None
        self._context = None
        self._page = None
        # None => use the configured default; pass False to force a visible window.
        self._headless = settings.whatsapp_headless if headless is None else headless

    # ---- lifecycle ----

    def __enter__(self) -> "WhatsAppWebSender":
        self._pw = sync_playwright().start()
        session_dir = Path(settings.whatsapp_session_dir).resolve()
        session_dir.mkdir(parents=True, exist_ok=True)
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=self._headless,
            args=["--disable-blink-features=AutomationControlled"],
            timeout=60000,  # never hang forever if the profile is busy
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._context:
                self._context.close()
        finally:
            if self._pw:
                self._pw.stop()

    # ---- auth ----

    def ensure_logged_in(self, qr_wait_seconds: int = 120) -> bool:
        """Open WhatsApp Web; if QR is shown, wait for the user to scan it."""
        page = self._page
        page.goto(WA_BASE, wait_until="domcontentloaded", timeout=60000)
        # Chat list pane only appears once logged in (stable selector).
        chat_ready = '#pane-side, div[aria-label="Chat list"]'
        qr = 'canvas[aria-label*="Scan"], div[data-ref]'
        try:
            page.wait_for_selector(chat_ready, timeout=15000)
            logger.info("WhatsApp Web: already logged in.")
            return True
        except PWTimeout:
            pass

        # Fast path: caller doesn't want to wait for a fresh QR scan here.
        if qr_wait_seconds <= 0:
            logger.error("WhatsApp Web: not logged in (use Connect to scan the QR first).")
            return False

        # Need QR scan.
        try:
            page.wait_for_selector(qr, timeout=10000)
            logger.warning(
                "WhatsApp Web: scan the QR code with {} (waiting up to {}s)...",
                settings.whatsapp_sender_number or "your phone",
                qr_wait_seconds,
            )
        except PWTimeout:
            logger.error("WhatsApp Web: neither chat list nor QR appeared.")
            return False

        try:
            page.wait_for_selector(chat_ready, timeout=qr_wait_seconds * 1000)
            logger.info("WhatsApp Web: login successful.")
            return True
        except PWTimeout:
            logger.error("WhatsApp Web: QR not scanned in time.")
            return False

    # ---- sending ----

    def send(self, phone: str, message: str, dial_code: str | None = None) -> SendResult:
        """Send one message to a phone number, using `dial_code` for normalization."""
        normalized = normalize_phone(phone, dial_code)
        if not normalized:
            return SendResult(phone=phone, ok=False, error="invalid phone number")

        if settings.whatsapp_dry_run:
            logger.info("[DRY-RUN] would send to {}: {}", normalized, message[:60])
            return SendResult(phone=normalized, ok=True, dry_run=True)

        page = self._page
        url = (
            f"{WA_BASE}/send?phone={normalized}"
            f"&text={urllib.parse.quote(message)}"
        )
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Wait for either the compose box (chat opened) or an invalid-number popup.
            compose = 'div[contenteditable="true"][data-tab="10"], footer div[contenteditable="true"]'
            for _ in range(45):
                try:
                    if page.get_by_text(
                        re.compile("phone number shared via url is invalid", re.I)
                    ).count():
                        return SendResult(
                            phone=normalized, ok=False, error="number not on WhatsApp"
                        )
                except Exception:
                    pass
                if page.locator(compose).count():
                    break
                time.sleep(1)
            else:
                return SendResult(
                    phone=normalized, ok=False, error="send timeout (chat didn't open)"
                )

            time.sleep(random.uniform(1.0, 2.0))

            # Preferred: click the send button; fallback: focus compose + Enter.
            sent = False
            for sel in ('button[aria-label="Send"]', 'span[data-icon="send"]', 'button[data-tab="11"]'):
                try:
                    btn = page.locator(sel).first
                    if btn.count():
                        btn.click(timeout=5000)
                        sent = True
                        break
                except Exception:
                    continue
            if not sent:
                try:
                    page.locator(compose).first.click()
                    page.keyboard.press("Enter")
                    sent = True
                except Exception:
                    pass

            if not sent:
                return SendResult(phone=normalized, ok=False, error="could not find send control")

            time.sleep(random.uniform(2.0, 4.0))  # let it flush
            logger.info("Sent WhatsApp to {}", normalized)
            return SendResult(phone=normalized, ok=True)
        except PWTimeout:
            return SendResult(phone=normalized, ok=False, error="send timeout (chat didn't load)")
        except Exception as exc:
            return SendResult(phone=normalized, ok=False, error=str(exc))

    def throttle(self) -> None:
        """Randomized human-like delay between messages."""
        time.sleep(random.uniform(settings.whatsapp_delay_min, settings.whatsapp_delay_max))
