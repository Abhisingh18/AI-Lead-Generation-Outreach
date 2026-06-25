"""Background scrape job so the API stays responsive during long pipelines.

Problem this solves: scraping + per-lead LLM audits take minutes. If that runs
directly inside the request, it blocks FastAPI's event loop and the dashboard
can't load anything (shows 0 / "failed to fetch"). Here the scrape runs as an
asyncio background task, and each lead's sync pipeline work is pushed to a worker
thread, so the dashboard can read leads live as they are committed.
"""

from __future__ import annotations

import asyncio
import threading

from loguru import logger

from app.database import SessionLocal
from app.models import Business
from app.scrapers.google_maps import ScrapedBusiness
from app.services.pipeline import process_business, upsert_business


class ScrapeJob:
    def __init__(self) -> None:
        self.running = False
        self.phase = "idle"          # idle | scraping | processing | done | error
        self.total = 0
        self.done = 0
        self.city = ""
        self.category = ""
        self.country = ""
        self.error: str | None = None
        self._task: asyncio.Task | None = None

    def snapshot(self) -> dict:
        return {
            "running": self.running,
            "phase": self.phase,
            "total": self.total,
            "done": self.done,
            "city": self.city,
            "category": self.category,
            "country": self.country,
            "error": self.error,
        }

    def start(
        self,
        city: str,
        category: str,
        max_results: int | None,
        country: str | None,
        dial_code: str,
        run_pipeline: bool,
    ) -> dict:
        if self.running:
            return {"started": False, **self.snapshot()}
        self.running = True
        self.phase = "scraping"
        self.total = 0
        self.done = 0
        self.city = city
        self.category = category
        self.country = country or ""
        self.error = None
        self._task = asyncio.create_task(
            self._run(city, category, max_results, country, dial_code, run_pipeline)
        )
        return {"started": True, **self.snapshot()}

    async def _run(
        self,
        city: str,
        category: str,
        max_results: int | None,
        country: str | None,
        dial_code: str,
        run_pipeline: bool,
    ) -> None:
        # Imported lazily so importing this module doesn't require Playwright.
        from app.scrapers.google_maps import scrape_google_maps

        try:
            scraped = await scrape_google_maps(
                city, category, max_results, country=country, dial_code=dial_code
            )
            self.total = len(scraped)

            # Phase 1: save ALL leads quickly so they appear in the dashboard at once.
            biz_ids: list[int] = []
            for sb in scraped:
                bid = await asyncio.to_thread(self._save, sb)
                if bid:
                    biz_ids.append(bid)

            # Phase 2: run the AI pipeline with limited concurrency (much faster).
            if run_pipeline and biz_ids:
                self.phase = "processing"
                sem = asyncio.Semaphore(4)  # 4 leads audited/written at a time

                async def _proc(bid: int) -> None:
                    async with sem:
                        await asyncio.to_thread(self._process_one, bid)
                        self.done += 1

                await asyncio.gather(*(_proc(b) for b in biz_ids))
            else:
                self.done = len(biz_ids)

            self.phase = "done"
            logger.info("Scrape job done: {}/{} for '{}' in {}", self.done, self.total, category, city)
        except Exception as exc:
            logger.exception("Scrape job failed")
            self.error = str(exc)
            self.phase = "error"
        finally:
            self.running = False

    @staticmethod
    def _save(sb: ScrapedBusiness) -> int | None:
        """Quickly persist a scraped business (no LLM). Returns its id."""
        db = SessionLocal()
        try:
            biz = upsert_business(db, sb)
            if biz is None:  # already contacted — skip
                return None
            db.commit()
            return biz.id
        except Exception:
            db.rollback()
            logger.exception("Failed saving '{}'", getattr(sb, "name", "?"))
            return None
        finally:
            db.close()

    @staticmethod
    def _process_one(business_id: int) -> None:
        """Run the AI pipeline (audit + message) for one saved business."""
        db = SessionLocal()
        try:
            biz = db.get(Business, business_id)
            if biz:
                process_business(db, biz)
        except Exception:
            db.rollback()
            logger.exception("Failed processing business id {}", business_id)
        finally:
            db.close()


# Module-level singleton
scrape_job = ScrapeJob()


class SendJob:
    """Background WhatsApp send job (sync Playwright runs in its own thread)."""

    def __init__(self) -> None:
        self.running = False
        self.phase = "idle"     # idle | sending | done | error
        self.total = 0
        self.done = 0
        self.sent = 0
        self.error: str | None = None
        self.results: list[dict] = []
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict:
        return {
            "running": self.running,
            "phase": self.phase,
            "total": self.total,
            "done": self.done,
            "sent": self.sent,
            "error": self.error,
            "results": self.results[-50:],
        }

    def start(self, limit: int | None, min_score: int, only_whatsapp: bool = True) -> dict:
        from app.config import settings
        from app.senders.wa_login_manager import login_manager

        if self.running:
            return {"started": False, **self.snapshot()}

        # For real sends, don't fight the login window for the browser profile.
        if not settings.whatsapp_dry_run and login_manager.snapshot()["status"] in (
            "starting",
            "waiting_qr",
        ):
            return {
                "started": False,
                "error": "Finish WhatsApp login (scan the QR) before sending.",
                **self.snapshot(),
            }

        self.running = True
        self.phase = "sending"
        self.total = 0
        self.done = 0
        self.sent = 0
        self.error = None
        self.results = []
        self._thread = threading.Thread(
            target=self._run, args=(limit, min_score, only_whatsapp), daemon=True
        )
        self._thread.start()
        return {"started": True, **self.snapshot()}

    def _run(self, limit: int | None, min_score: int, only_whatsapp: bool) -> None:
        from app.services.sending import send_batch

        def _progress(done: int, total: int, sent: int) -> None:
            self.done, self.total, self.sent = done, total, sent

        db = SessionLocal()
        try:
            self.results = send_batch(
                db,
                limit=limit,
                min_score=min_score,
                on_progress=_progress,
                only_whatsapp=only_whatsapp,
            )
            self.sent = sum(1 for r in self.results if r.get("ok"))
            self.phase = "done"
            logger.info("Send job done: {}/{} sent.", self.sent, self.total)
        except Exception as exc:
            logger.exception("Send job failed")
            self.error = str(exc)
            self.phase = "error"
        finally:
            db.close()
            self.running = False


# Module-level singleton
send_job = SendJob()


class EmailSendJob:
    """Background email send job (SMTP, no browser)."""

    def __init__(self) -> None:
        self.running = False
        self.phase = "idle"
        self.total = 0
        self.done = 0
        self.sent = 0
        self.error: str | None = None
        self.results: list[dict] = []
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict:
        return {
            "running": self.running,
            "phase": self.phase,
            "total": self.total,
            "done": self.done,
            "sent": self.sent,
            "error": self.error,
            "results": self.results[-50:],
        }

    def start(self, limit: int | None, min_score: int) -> dict:
        if self.running:
            return {"started": False, **self.snapshot()}
        self.running = True
        self.phase = "sending"
        self.total = self.done = self.sent = 0
        self.error = None
        self.results = []
        self._thread = threading.Thread(
            target=self._run, args=(limit, min_score), daemon=True
        )
        self._thread.start()
        return {"started": True, **self.snapshot()}

    def _run(self, limit: int | None, min_score: int) -> None:
        from app.services.sending import send_email_batch

        def _progress(done: int, total: int, sent: int) -> None:
            self.done, self.total, self.sent = done, total, sent

        db = SessionLocal()
        try:
            self.results = send_email_batch(
                db, limit=limit, min_score=min_score, on_progress=_progress
            )
            self.sent = sum(1 for r in self.results if r.get("ok"))
            self.phase = "done"
            logger.info("Email job done: {}/{} sent.", self.sent, self.total)
        except Exception as exc:
            logger.exception("Email job failed")
            self.error = str(exc)
            self.phase = "error"
        finally:
            db.close()
            self.running = False


email_job = EmailSendJob()
