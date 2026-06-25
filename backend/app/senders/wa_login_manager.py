"""Background WhatsApp login manager — opens WhatsApp Web for the dashboard.

WhatsApp Web does NOT render the QR reliably in headless mode, so we open a real
(visible) Chromium window. The user can scan the QR directly in that window; we
also try to mirror the QR into the dashboard. Once scanned, login is persisted to
disk (WHATSAPP_SESSION_DIR) and the window closes so the sender can reuse it.

Playwright's sync objects are thread-affine, so a dedicated worker thread owns the
browser session and exposes a thread-safe snapshot the HTTP endpoints poll.
"""

from __future__ import annotations

import base64
import re
import threading
import time
from pathlib import Path

from loguru import logger
from playwright.sync_api import sync_playwright

WA_BASE = "https://web.whatsapp.com"
# Logged-in indicator: the chat list pane (stable across WhatsApp Web versions).
CHAT_READY = '#pane-side, div[aria-label="Chat list"]'
# 8-char linking code shown as "XXXX-XXXX".
LINK_CODE_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b")


class _LoginManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.status = "idle"   # idle|starting|waiting_qr|waiting_code|logged_in|error
        self.qr_data_url: str | None = None
        self.link_code: str | None = None  # for "link with phone number" (mobile)
        self.error: str | None = None

    def snapshot(self) -> dict:
        return {
            "status": self.status,
            "logged_in": self.status == "logged_in",
            "qr": self.qr_data_url,
            "link_code": self.link_code,
            "error": self.error,
        }

    def start(self) -> dict:
        from app.config import settings

        if not settings.whatsapp_enabled:
            self.status = "disabled"
            self.error = (
                "WhatsApp needs a real browser/screen, so it's disabled on the cloud "
                "server. Use Email here, or run the backend on your laptop for WhatsApp."
            )
            return self.snapshot()
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.snapshot()
            self.status = "starting"
            self.qr_data_url = None
            self.link_code = None
            self.error = None
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self.snapshot()

    # ---- worker ----

    def _run(self, max_wait: int = 180) -> None:
        from app.config import settings

        session_dir = Path(settings.whatsapp_session_dir).resolve()
        session_dir.mkdir(parents=True, exist_ok=True)
        logger.info("WhatsApp login: launching browser (profile: {})", session_dir)
        try:
            with sync_playwright() as pw:
                ctx = pw.chromium.launch_persistent_context(
                    user_data_dir=str(session_dir),
                    headless=False,  # WhatsApp Web only renders the QR in a real browser
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1000, "height": 760},
                    locale="en-IN",
                    timeout=60000,
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(WA_BASE, wait_until="domcontentloaded", timeout=60000)
                logger.info("WhatsApp login: page loaded.")

                # Give WhatsApp Web a moment to render the QR canvas.
                try:
                    page.wait_for_selector('canvas, div[data-ref]', timeout=20000)
                except Exception:
                    pass

                # Mobile-friendly: if a sender number is set, switch to the
                # "link with phone number" flow and surface the 8-char code.
                if settings.whatsapp_sender_number:
                    self._try_phone_code(page, settings.whatsapp_sender_number)

                if self.status not in ("logged_in", "waiting_code"):
                    self.status = "waiting_qr"

                deadline = time.time() + max_wait
                while time.time() < deadline:
                    if page.locator(CHAT_READY).count():
                        self.status = "logged_in"
                        self.qr_data_url = None
                        self.link_code = None
                        logger.info("WhatsApp login: SUCCESS (logged in).")
                        break
                    if self.status == "waiting_code":
                        # Refresh the captured code (it can rotate) and keep waiting.
                        self._read_code(page)
                    else:
                        png = self._grab_qr(page)
                        if png:
                            self.qr_data_url = "data:image/png;base64," + base64.b64encode(
                                png
                            ).decode()
                    time.sleep(2.0)
                else:
                    if self.status != "logged_in":
                        self.status = "error"
                        self.error = "QR not scanned in time"
                        logger.warning("WhatsApp login: timed out waiting for scan.")

                ctx.close()
        except Exception as exc:
            logger.exception("WhatsApp login manager failed")
            self.status = "error"
            self.error = str(exc)

    @staticmethod
    def _grab_qr(page) -> bytes | None:
        """Capture the QR for the dashboard. Falls back to a full-page screenshot
        so the user can always scan it from the dashboard, even if the actual
        browser window is not visible on their screen."""
        for sel in (
            'div[data-ref]',                 # the QR container box
            'canvas[aria-label*="scan" i]',
            'div[data-ref] canvas',
            "canvas",
        ):
            try:
                loc = page.locator(sel).first
                if loc.count():
                    shot = loc.screenshot(timeout=4000)
                    if shot:
                        return shot
            except Exception:
                continue
        # Last resort: whole page (QR is the main element on the login screen).
        try:
            return page.screenshot(timeout=5000)
        except Exception:
            return None

    def _try_phone_code(self, page, number: str) -> None:
        """Switch WhatsApp Web to 'log in with phone number' and capture the code.

        Lets a user connect with ONLY their phone (no second screen to scan a QR).
        Best-effort: if anything fails, we leave the QR flow intact.
        """
        national = re.sub(r"\D", "", number).lstrip("0")
        try:
            btn = page.get_by_role("button", name=re.compile("phone number", re.I))
            if not btn.count():
                btn = page.get_by_text(re.compile("log in with phone number", re.I))
            if not btn.count():
                return
            btn.first.click(timeout=8000)
            page.wait_for_timeout(1500)

            # Fill the phone number (locale en-IN defaults the country to +91).
            inp = page.locator('input[aria-label*="phone" i]')
            if not inp.count():
                inp = page.get_by_role("textbox")
            inp.first.click()
            inp.first.fill(national, timeout=5000)
            page.wait_for_timeout(500)

            nxt = page.get_by_role("button", name=re.compile(r"^\s*next\s*$", re.I))
            if nxt.count():
                nxt.first.click(timeout=8000)
            page.wait_for_timeout(3000)

            self._read_code(page)
            if self.link_code:
                self.status = "waiting_code"
                logger.info("WhatsApp login: phone-link code ready: {}", self.link_code)
            else:
                # Could not read the code; show a screenshot of the code screen.
                png = self._grab_qr(page)
                if png:
                    self.qr_data_url = "data:image/png;base64," + base64.b64encode(
                        png
                    ).decode()
                    self.status = "waiting_code"
        except Exception as exc:
            logger.warning("Phone-link flow failed, falling back to QR: {}", exc)

    def _read_code(self, page) -> None:
        """Extract the 8-character linking code from the page."""
        try:
            # Codes often sit in elements with aria-details/data-link-code.
            for sel in ('[data-link-code]', '[aria-details]'):
                loc = page.locator(sel).first
                if loc.count():
                    val = (loc.get_attribute("data-link-code") or
                           loc.inner_text(timeout=2000) or "")
                    m = LINK_CODE_RE.search(val.upper().replace(" ", ""))
                    if m:
                        self.link_code = m.group(1)
                        return
            # Fallback: scan visible text for an XXXX-XXXX code.
            body = page.inner_text("body", timeout=3000)
            m = LINK_CODE_RE.search(body.upper())
            if m:
                self.link_code = m.group(1)
        except Exception:
            pass


# Module-level singleton
login_manager = _LoginManager()
