"""Central application configuration, loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All tunable settings for the platform. Values come from .env / environment."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---------- Database ----------
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/leadgen"

    # ---------- LLM ----------
    llm_provider: Literal["zhipu", "openrouter"] = "zhipu"

    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_model: str = "glm-4.5-flash"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "deepseek/deepseek-chat"

    # ---------- Scraper ----------
    scraper_headless: bool = True
    scraper_max_results: int = 20
    scraper_delay_min: float = 2.0
    scraper_delay_max: float = 5.0

    # ---------- WhatsApp sender (Playwright + WhatsApp Web) ----------
    whatsapp_sender_number: str = ""          # your own WA number, e.g. 9648531091
    whatsapp_country_code: str = "91"          # default India
    whatsapp_session_dir: str = ".wa_session"  # persistent browser profile (QR once)
    whatsapp_headless: bool = False            # keep False for first QR login
    whatsapp_dry_run: bool = True              # True = don't actually send (safe default)
    whatsapp_daily_limit: int = 30             # anti-ban safety cap per run
    whatsapp_delay_min: float = 8.0            # seconds between sends
    whatsapp_delay_max: float = 20.0

    # ---------- Agency (your company — used in outreach messages) ----------
    agency_name: str = "Pragyaan Labs"
    agency_website: str = "https://www.pragyaanlabs.space/"
    agency_sender_name: str = "Abhishek Singh"   # who the message is from
    agency_founder_note: str = "Founder, Pragyaan Labs (IIT Madras)"  # trust signal
    agency_calendar_url: str = ""  # booking link added to outreach as the CTA
    # What the agency actually offers (used to pitch real services in outreach).
    agency_services: str = (
        "AI agents & agentic automation, AI voice agents, AI chatbots, WhatsApp "
        "automation, custom websites & mobile apps, RAG/LLM systems, predictive AI, "
        "SEO & digital marketing, and custom SaaS products — from prototype to "
        "production. We also build full websites for businesses that don't have one."
    )
    # Primary market focus for tone (e.g. "foreign/international clients").
    agency_target_market: str = "international clients (US, UK, EU, Gulf, Australia)"

    # ---------- Email (Gmail SMTP) ----------
    email_enabled: bool = True
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465            # SSL
    email_sender: str = ""          # e.g. abhi964800@gmail.com
    email_app_password: str = ""    # 16-char Gmail App Password (NOT your login pwd)
    email_dry_run: bool = True      # True = don't actually send (safe default)
    email_daily_limit: int = 50

    # Brevo (Sendinblue) failover — used automatically when Gmail hits its quota.
    brevo_smtp_host: str = "smtp-relay.brevo.com"
    brevo_smtp_port: int = 587      # STARTTLS
    brevo_login: str = ""           # Brevo SMTP login (from Brevo dashboard)
    brevo_smtp_key: str = ""        # Brevo SMTP key / master password
    email_failover: bool = True     # try Brevo if Gmail fails with a quota/limit error

    # ---------- App ----------
    app_env: str = "development"
    log_level: str = "INFO"

    @property
    def active_llm(self) -> dict[str, str]:
        """Return the (api_key, base_url, model) for the currently selected provider."""
        if self.llm_provider == "openrouter":
            return {
                "api_key": self.openrouter_api_key,
                "base_url": self.openrouter_base_url,
                "model": self.openrouter_model,
            }
        return {
            "api_key": self.zhipu_api_key,
            "base_url": self.zhipu_base_url,
            "model": self.zhipu_model,
        }


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor so the .env is parsed only once."""
    return Settings()


settings = get_settings()
